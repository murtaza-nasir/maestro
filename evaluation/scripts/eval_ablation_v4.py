"""
Ablation Study v4: Two-Prompt Full Pipeline Evaluation
=======================================================
Evaluates WRITER's end-to-end output quality across 0, 1, 2 reflection rounds
using a two-prompt evaluation architecture with 3-judge panel.

Pipeline per run:
  1. ResearchAgent gathers notes (with 0/1/2 reflection rounds)
  2. WritingAgent produces final text from accumulated notes
  3. PROMPT 1 — Note Faithfulness: checks each note against its DB source chunks
  4. PROMPT 2 — Full Evaluation: segments text, traces claims, scores rubric
     (uses Prompt 1 results + ground truth summary for coverage)

Usage: docker cp eval_ablation_v4.py maestro-backend:/app/eval_ablation_v4.py
       docker exec maestro-backend python /app/eval_ablation_v4.py

Output: evaluation/results/ablation_v4_results_<timestamp>.json
"""

import os, sys, asyncio, time, logging, json, hashlib, datetime, re
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

os.environ.pop('CUDA_VISIBLE_DEVICES', None)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
sys.path.insert(0, '/app')

# ── Setup user context ─────────────────────────────────────────────
import urllib.parse, psycopg2
db_url = os.environ.get("DATABASE_URL", "")
parsed = urllib.parse.urlparse(db_url)
conn = psycopg2.connect(host=parsed.hostname, port=parsed.port,
                        dbname=parsed.path[1:], user=parsed.username,
                        password=parsed.password)
cur = conn.cursor()
cur.execute("SELECT id, username, settings FROM users WHERE id = 1")
row = cur.fetchone()
USER_ID, USERNAME, USER_SETTINGS = row
conn.close()

class MockUser:
    def __init__(self, uid, uname, settings):
        self.id = uid; self.username = uname; self.settings = settings

from ai_researcher.user_context import set_current_user
set_current_user(MockUser(USER_ID, USERNAME, USER_SETTINGS))

# ── Imports ────────────────────────────────────────────────────────
from ai_researcher import config
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.tool_registry import ToolRegistry, ToolDefinition
from ai_researcher.agentic_layer.agents.research_agent import ResearchAgent
from ai_researcher.agentic_layer.agents.writing_agent import WritingAgent
from ai_researcher.agentic_layer.schemas.planning import ReportSection
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.core_rag.embedder import TextEmbedder
from ai_researcher.core_rag.pgvector_store import PGVectorStore
from ai_researcher.core_rag.reranker import TextReranker
from ai_researcher.core_rag.retriever import Retriever
from ai_researcher.core_rag.query_preparer import QueryPreparer
from ai_researcher.core_rag.query_strategist import QueryStrategist
from ai_researcher.agentic_layer.tools.document_search import DocumentSearchTool
from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool
from ai_researcher.agentic_layer.tools.web_page_fetcher_tool import WebPageFetcherTool
from ai_researcher.agentic_layer.tools.file_reader_tool import FileReaderTool
from ai_researcher.agentic_layer.tools.calculator_tool import CalculatorTool

# ── Configuration ──────────────────────────────────────────────────
MODELS_TO_TEST = [
    "google/gemini-2.5-flash-lite",
    "qwen/qwen3.5-27b",
    "google/gemma-3-27b-it",
]

REFLECTION_ROUNDS = [0, 1, 2]

JUDGE_MODELS = [
    "anthropic/claude-sonnet-4-6",
    "qwen/qwen3.5-397b-a17b",
    "z-ai/glm-5-turbo",
]

# Load questions
QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "evaluation_questions.json")
if not os.path.exists(QUESTIONS_FILE):
    QUESTIONS_FILE = "/app/evaluation_questions.json"

with open(QUESTIONS_FILE) as _f:
    _qdata = json.load(_f)

EVAL_QUESTIONS = _qdata["questions"]
QUESTIONS = [q["question"] for q in EVAL_QUESTIONS]
QUESTION_META = {q["question"]: q for q in EVAL_QUESTIONS}

RESULTS_DIR = "/app/evaluation/results"
os.makedirs(RESULTS_DIR, exist_ok=True)


# ── Cost Tracker ──────────────────────────────────────────────────
class CostTracker:
    def __init__(self):
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0
        self.calls = []

    def record(self, metadata: Optional[Dict], label: str = ""):
        if not metadata:
            return
        pt = metadata.get("prompt_tokens", 0) or 0
        ct = metadata.get("completion_tokens", 0) or 0
        cost = float(metadata.get("cost", 0) or 0)
        self.total_prompt_tokens += pt
        self.total_completion_tokens += ct
        self.total_cost += cost
        self.calls.append({"label": label, "model": metadata.get("model_name", ""),
                           "prompt_tokens": pt, "completion_tokens": ct, "cost": cost})

    def summary(self) -> Dict:
        groups: Dict[str, Dict] = {}
        for c in self.calls:
            lbl = c["label"] or "other"
            if lbl not in groups:
                groups[lbl] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
            groups[lbl]["calls"] += 1
            groups[lbl]["prompt_tokens"] += c["prompt_tokens"]
            groups[lbl]["completion_tokens"] += c["completion_tokens"]
            groups[lbl]["cost"] += c["cost"]
        for g in groups.values():
            g["cost"] = round(g["cost"], 6)
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_cost_usd": round(self.total_cost, 6),
            "total_api_calls": len(self.calls),
            "cost_by_label": groups
        }

cost_tracker = CostTracker()


# ── JSON Repair ───────────────────────────────────────────────────
def repair_json(text: str) -> Optional[Dict]:
    """Robustly extract and parse JSON from LLM output."""
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text.strip())

    start = text.find('{')
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    end = start
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    raw = text[start:end]
    if not raw:
        return None

    for attempt_fn in [
        lambda t: json.loads(t),
        lambda t: json.loads(re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', re.sub(r',\s*([}\]])', r'\1', t))),
        lambda t: json.loads(re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', re.sub(r',\s*([}\]])', r'\1', t)), strict=False),
    ]:
        try:
            return attempt_fn(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


# ── Global components ──────────────────────────────────────────────
model_dispatcher = None
tool_registry = None
research_agent = None
writing_agent = None

def initialize():
    global model_dispatcher, tool_registry, research_agent, writing_agent
    logging.info("Initializing components...")
    sem = asyncio.Semaphore(10)
    model_dispatcher = ModelDispatcher(user_settings=USER_SETTINGS, semaphore=sem)
    embedder = TextEmbedder()
    vs = PGVectorStore()
    reranker = TextReranker()
    retriever = Retriever(embedder, vs, reranker)
    qp = QueryPreparer(model_dispatcher)
    qs = QueryStrategist(model_dispatcher)
    tool_registry = ToolRegistry()
    for tool_cls, args in [
        (DocumentSearchTool, (retriever, qp, qs)),
        (WebSearchTool, ()), (WebPageFetcherTool, ()),
        (FileReaderTool, ()), (CalculatorTool, ()),
    ]:
        tool = tool_cls(*args)
        tool_registry.register_tool(ToolDefinition(
            name=tool.name, description=tool.description,
            parameters_schema=tool.parameters_schema, implementation=tool.execute))
    research_agent = ResearchAgent(
        model_dispatcher=model_dispatcher, tool_registry=tool_registry, query_preparer=qp)
    writing_agent = WritingAgent(model_dispatcher=model_dispatcher)
    logging.info("All components initialized.")


# ── DB Chunk Lookup ────────────────────────────────────────────────
def fetch_chunks_from_db(chunk_ids: List[str]) -> Dict[str, str]:
    if not chunk_ids:
        return {}
    conn = psycopg2.connect(host=parsed.hostname, port=parsed.port,
                            dbname=parsed.path[1:], user=parsed.username,
                            password=parsed.password)
    cur = conn.cursor()
    result = {}
    for cid in chunk_ids:
        if not cid:
            continue
        try:
            cur.execute("SELECT chunk_text FROM document_chunks WHERE id = %s::uuid", (cid,))
            row = cur.fetchone()
            if row and row[0]:
                result[cid] = row[0].strip()
        except Exception:
            pass
    conn.close()
    return result


def fetch_chunks_by_doc_id(doc_id: str, limit: int = 5) -> List[str]:
    if not doc_id:
        return []
    conn = psycopg2.connect(host=parsed.hostname, port=parsed.port,
                            dbname=parsed.path[1:], user=parsed.username,
                            password=parsed.password)
    cur = conn.cursor()
    try:
        cur.execute("SELECT chunk_text FROM document_chunks WHERE doc_id = %s::uuid ORDER BY chunk_index LIMIT %s",
                    (doc_id, limit))
        chunks = [row[0].strip() for row in cur.fetchall() if row[0]]
    except Exception:
        chunks = []
    conn.close()
    return chunks


def get_source_chunks_for_note(note, fallback_context: str) -> str:
    """Get actual source chunks for a note from the database."""
    chunk_texts = []

    if hasattr(note, 'source_metadata'):
        chunk_ids = getattr(note.source_metadata, 'original_chunk_ids', None) or []
        if chunk_ids:
            fetched = fetch_chunks_from_db(chunk_ids)
            chunk_texts.extend(fetched.values())

    if not chunk_texts and hasattr(note, 'source_id') and note.source_id:
        if getattr(note, 'source_type', '') == 'document':
            fetched = fetch_chunks_from_db([note.source_id])
            chunk_texts.extend(fetched.values())

    if not chunk_texts and hasattr(note, 'source_metadata'):
        doc_id = getattr(note.source_metadata, 'doc_id', '') or ''
        if doc_id:
            chunk_texts.extend(fetch_chunks_by_doc_id(doc_id, limit=3))

    if not chunk_texts and fallback_context:
        chunk_texts.append(fallback_context)

    return "\n---\n".join(chunk_texts) if chunk_texts else "(no source chunks found)"


# ── Stage 1: Research ──────────────────────────────────────────────
async def run_research_pass(question: str, model: str, mission_id: str) -> List[Tuple]:
    section = ReportSection(
        section_id=f"abl_{hashlib.md5(question.encode()).hexdigest()[:8]}",
        title=f"Research: {question[:50]}", description=question,
        subsections=[], research_strategy="research_based")
    try:
        result = await research_agent.run_and_capture_context(
            mission_id=mission_id, section=section, focus_questions=[question],
            agent_scratchpad=None, feedback_callback=None, log_queue=None,
            update_callback=None, tool_registry=tool_registry, model=model,
            active_goals=None, active_thoughts=None)
        notes_tuples, exec_details, scratchpad = result
        return notes_tuples if notes_tuples else []
    except Exception as e:
        logging.error(f"Research pass error: {e}")
        return []


async def run_reflection_pass(question: str, notes_tuples: List[Tuple],
                               model: str, round_num: int) -> List[Tuple]:
    note_summaries = [n.content[:200] for n, c in notes_tuples if hasattr(n, 'content')]
    context_hint = "; ".join(note_summaries[:5])
    refined_q = (f"{question} (Round {round_num+1}: We already have evidence about: "
                 f"{context_hint[:500]}. Find additional perspectives, contradictory "
                 f"evidence, or deeper analysis.)")
    mission_id = f"abl_r{round_num}_{hashlib.md5(question.encode()).hexdigest()[:8]}"
    new_tuples = await run_research_pass(refined_q, model, mission_id)
    return notes_tuples + new_tuples


# ── Stage 2: Writing ──────────────────────────────────────────────
async def run_writing(question: str, notes_tuples: List[Tuple], model: str) -> Tuple[Optional[str], Optional[Dict]]:
    section = ReportSection(
        section_id=f"eval_{hashlib.md5(question.encode()).hexdigest()[:8]}",
        title=question[:80], description=question,
        subsections=[], research_strategy="research_based")
    notes_list = [note for note, ctx in notes_tuples]
    try:
        result = await writing_agent.run(
            section_to_write=section, notes_for_section=notes_list,
            previous_sections_content={}, full_outline=[section],
            mission_id=f"eval_write_{hashlib.md5(question.encode()).hexdigest()[:8]}",
            model=model, active_goals=None, active_thoughts=None)
        generated_text, model_details, scratchpad = result
        cost_tracker.record(model_details, label=f"writing:{model}")
        return generated_text, model_details
    except Exception as e:
        logging.error(f"Writing agent error: {e}")
        return None, None


# ── Prompt 1: Note Faithfulness ────────────────────────────────────
PROMPT1_TEMPLATE = """You are an expert fact-checker. For each research note below, decompose it into individual statements and check each against the source chunks.

A note may be based on MULTIPLE source chunks. A statement is "grounded" if it can be traced to content in ANY of its source chunks.

For each note:
1. Break it into individual statements (factual claims, interpretations, conclusions)
2. For each statement, classify:
   - "grounded": The statement is directly supported by text in at least one source chunk
   - "synthesized": The statement combines information from multiple source chunks accurately
   - "inferred": The statement draws a reasonable logical conclusion from the chunks, but the conclusion itself is not explicitly stated
   - "extrapolated": The statement goes beyond what the chunks support — added interpretation or information not in the sources
   - "contradicts": The statement conflicts with the source chunks
3. Give an overall assessment for the note based on the breakdown

NOTES AND THEIR SOURCE CHUNKS:
{notes_with_chunks}

Return a JSON object:
{{
  "note_assessments": [
    {{
      "note_id": "note_xxx",
      "statements": [
        {{
          "statement": "the specific claim or assertion from the note",
          "classification": "grounded|synthesized|inferred|extrapolated|contradicts",
          "supporting_chunk_quote": "exact quote from a source chunk that supports this, or empty if unsupported"
        }}
      ],
      "overall_assessment": "faithful|mostly_faithful|mixed|mostly_extrapolated|extrapolated",
      "grounded_count": 0,
      "extrapolated_count": 0,
      "total_statements": 0
    }}
  ]
}}"""


# ── Prompt 2: Full Evaluation ──────────────────────────────────────
PROMPT2_TEMPLATE = """You are an expert academic evaluator performing a comprehensive quality assessment of an AI-generated research text.

═══════════════════════════════════════════════════════
ORIGINAL RESEARCH QUESTION:
{question}

GROUND TRUTH — What a correct answer SHOULD contain:
{ground_truth}
═══════════════════════════════════════════════════════

FINAL TEXT (produced by the AI writing agent):
<<<final_text>>>
{final_text}
<<</final_text>>>

═══════════════════════════════════════════════════════
RESEARCH NOTES (with pre-computed faithfulness assessments):
{notes_with_faithfulness}
═══════════════════════════════════════════════════════

Perform the following analysis:

## PART 1: Text Segmentation
Decompose the FINAL TEXT into segments. Every sentence or clause must be classified as exactly one type:
- "claim": A factual assertion that can be verified
- "hedging": Uncertainty language, caveats, limitations ("Further research is needed", "Evidence is limited")
- "transition": Connecting phrases between ideas ("Furthermore", "In contrast")
- "definition": Defining a term or concept
- "structural": Section headers, introductory framing, concluding summaries without factual assertions
- "synthesis": A statement that combines or integrates facts from multiple sources into a higher-level insight
- "inference": A logical conclusion drawn from the evidence that is not explicitly stated in any source

## PART 2: Claim & Synthesis Tracing
For each segment classified as "claim", "synthesis", or "inference":

**Step A — Final Text → Notes:** Does any research note support this?
- If YES: record which note_id(s). The note's pre-computed faithfulness tells you if it was "faithful" or "extrapolated".
- If NO: this is "unsupported" — it came from the model's parametric knowledge.

**Step B — Determine support level using the note's statement-level faithfulness:**
Each note has been decomposed into individual statements, each classified as grounded/synthesized/inferred/extrapolated/contradicts. Use the SPECIFIC STATEMENT in the note that supports this claim:
- "grounded": The claim traces to a note statement classified as "grounded" (directly from source chunk)
- "synthesized": The claim combines information from multiple note statements that are each "grounded" or "synthesized"
- "inferred": The claim traces to a note statement classified as "inferred" (logical conclusion from sources)
- "extrapolated": The claim traces to a note statement classified as "extrapolated" (beyond source evidence)
- "unsupported": Not supported by any note statement (parametric knowledge / hallucination)

For "hedging", "transition", "definition", "structural" segments, set support_level to "N/A".

## PART 3: Quality Assessment (strict rubric — score each dimension 1-5 WITH mandatory justification)

Use these exact rubric definitions. These match the human expert evaluation rubric so scores are directly comparable.

**Correctness** (Factual Accuracy) — Are the claims and statements factually accurate?
5=All claims appear factually accurate; no errors detected | 4=Minor inaccuracies that do not affect overall conclusions | 3=Some factual errors present, but main arguments hold | 2=Several factual errors that undermine parts of the analysis | 1=Pervasive factual errors; the report is unreliable

**Coverage** (Completeness) — Does the text address the research question comprehensively? Check against the GROUND TRUTH above.
5=Thorough coverage; all major aspects and ground truth points addressed | 4=Good coverage; most important aspects included, minor gaps | 3=Adequate coverage; addresses the core question but misses some important areas | 2=Partial coverage; significant aspects are missing | 1=Very incomplete; fails to address the question meaningfully

**Coherence** (Organization and Flow) — Is the text well-organized with logical flow?
5=Excellent organization; clear logical flow; well-structured | 4=Good organization; mostly logical flow with minor structural issues | 3=Adequate organization; some sections feel disjointed or repetitive | 2=Poor organization; difficult to follow; significant repetition | 1=Incoherent; no discernible logical structure

**Usefulness** (Practical Value) — Would a researcher find this useful as a starting point for understanding the topic or identifying relevant literature?
5=Highly useful; could serve as a solid foundation for further research | 4=Useful; provides valuable insights and good entry points into the literature | 3=Moderately useful; provides some value but requires significant supplementation | 2=Limited usefulness; a researcher would be better off starting from scratch | 1=Not useful; misleading or too superficial to provide any research value

**Citation Quality** (Source Support) — Are claims properly supported by cited sources? Do [doc_id] references appear relevant and appropriate?
5=Claims are well-supported; citations appear relevant and appropriately placed | 4=Most claims are supported; citations are generally appropriate | 3=Some claims lack citation support; some citations may be tangentially relevant | 2=Many unsupported claims; citations are frequently missing or seem irrelevant | 1=Very poor citation practices; most claims are unsupported

**Answer Relevance** (additional automated dimension) — Does the text actually ANSWER the question, not just discuss related topics?
5=Directly and thoroughly answers the question | 4=Mostly answers, minor tangents | 3=Partially answers, notable tangents | 2=Mostly tangential to the question | 1=Does not answer the question asked
YOU MUST quote specific passages from the final text that directly answer the question. If you cannot quote such passages, the score MUST be ≤2.

## PART 4: Hedging Analysis
- Does the text appropriately signal uncertainty when evidence is thin?
- Are there claims presented as definitive that should be hedged?
- For questions where the corpus may lack complete answers, does the text acknowledge limitations?

Return a single JSON object:
{{
  "segments": [
    {{
      "segment_id": 1,
      "text": "exact text from final output",
      "type": "claim|hedging|transition|definition|structural|synthesis|inference",
      "supporting_note_ids": ["note_xxx"],
      "support_level": "grounded|synthesized|inferred|extrapolated|unsupported|N/A",
      "explanation": "brief justification for classification and support level"
    }}
  ],
  "quality_scores": {{
    "correctness": {{"score": 4, "justification": "..."}},
    "coverage": {{"score": 4, "justification": "...", "ground_truth_points_addressed": ["point1", "point2"], "ground_truth_points_missing": ["point3"]}},
    "coherence": {{"score": 4, "justification": "..."}},
    "usefulness": {{"score": 4, "justification": "..."}},
    "citation_quality": {{"score": 4, "justification": "..."}},
    "answer_relevance": {{"score": 4, "justification": "...", "answering_passages": ["quoted text"]}}
  }},
  "hedging_analysis": {{
    "appropriate_hedging": true,
    "claims_needing_hedging": ["claims presented as definitive but lacking strong evidence"],
    "excessive_hedging": ["passages with unnecessary hedging"]
  }}
}}"""


# ── Judge Dispatch ─────────────────────────────────────────────────
CLAUDE_P1_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "note_faithfulness",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "note_assessments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "note_id": {"type": "string"},
                            "statements": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "statement": {"type": "string"},
                                        "classification": {"type": "string", "enum": ["grounded", "synthesized", "inferred", "extrapolated", "contradicts"]},
                                        "supporting_chunk_quote": {"type": "string"}
                                    },
                                    "required": ["statement", "classification", "supporting_chunk_quote"],
                                    "additionalProperties": False
                                }
                            },
                            "overall_assessment": {"type": "string", "enum": ["faithful", "mostly_faithful", "mixed", "mostly_extrapolated", "extrapolated"]},
                            "grounded_count": {"type": "integer"},
                            "extrapolated_count": {"type": "integer"},
                            "total_statements": {"type": "integer"}
                        },
                        "required": ["note_id", "statements", "overall_assessment", "grounded_count", "extrapolated_count", "total_statements"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["note_assessments"],
            "additionalProperties": False
        }
    }
}

BASIC_JSON_FORMAT = {"type": "json_object"}


async def call_judge(messages: List[Dict], judge_model: str, label: str,
                     claude_schema: Optional[Dict] = None) -> Dict:
    """Call a judge model and return parsed JSON.
    claude_schema: if provided, use this json_schema for Claude; otherwise use basic json_object."""
    if claude_schema and ("claude" in judge_model.lower() or "anthropic" in judge_model.lower()):
        resp_format = claude_schema
    else:
        resp_format = BASIC_JSON_FORMAT

    try:
        result = await model_dispatcher.dispatch(
            messages=messages, agent_mode="planning", model=judge_model,
            response_format=resp_format)

        if isinstance(result, tuple):
            response_obj, metadata = result
            cost_tracker.record(metadata, label=label)
            if response_obj is None:
                return {"error": "No response", "_judge": judge_model}
            content = response_obj.choices[0].message.content if hasattr(response_obj, 'choices') else str(response_obj)
        else:
            content = str(result)

        parsed = repair_json(content)
        if parsed:
            parsed["_judge"] = judge_model
            parsed["_raw_response"] = content  # Full response including thinking
            return parsed
        logging.error(f"JSON repair failed ({judge_model}): {content[:300]}")
        return {"error": "JSON repair failed", "_raw_response": content, "_judge": judge_model}
    except Exception as e:
        logging.error(f"Judge error ({judge_model}): {e}")
        return {"error": str(e), "_judge": judge_model}


# ── Prompt 1 Execution ─────────────────────────────────────────────
def format_notes_for_prompt1(notes_tuples: List[Tuple]) -> Tuple[str, List[Dict]]:
    """Format notes with DB chunks for Prompt 1. Returns formatted text and note metadata."""
    parts = []
    note_meta = []
    count = 0
    for i, (note, fallback_ctx) in enumerate(notes_tuples):
        note_id = note.note_id if hasattr(note, 'note_id') else f"note_{i}"
        note_content = note.content if hasattr(note, 'content') else str(note)

        # Clean up common markdown prefixes instead of skipping
        note_content = note_content.strip()
        for prefix in ['**Note:**', '**Note**:', 'Agent Scratchpad:', '**Research Note:**']:
            if note_content.startswith(prefix):
                note_content = note_content[len(prefix):].strip()

        # Only skip truly empty notes
        if not note_content or len(note_content) < 10:
            continue

        source_chunks = get_source_chunks_for_note(note, fallback_ctx)
        doc_id = getattr(note.source_metadata, 'doc_id', '') if hasattr(note, 'source_metadata') else ''
        title = getattr(note.source_metadata, 'title', '') if hasattr(note, 'source_metadata') else ''

        count += 1
        parts.append(
            f"--- NOTE {count} ---\n"
            f"Note ID: {note_id}\n"
            f"Document: {title} [{(doc_id or '')[:8]}]\n"
            f"Note Content: {note_content}\n"
            f"Source Chunks:\n{source_chunks[:3000]}\n"
        )
        note_meta.append({"note_id": note_id, "content": note_content[:500],
                          "doc_id": doc_id, "title": title})

    return "\n".join(parts), note_meta


async def run_prompt1(notes_tuples: List[Tuple]) -> Tuple[Dict[str, Dict], List[Dict]]:
    """Run Prompt 1 across all judges. Returns (aggregated faithfulness, raw results)."""
    notes_formatted, note_meta = format_notes_for_prompt1(notes_tuples)

    if not notes_formatted:
        return {}, []

    if len(notes_formatted) > 80000:
        notes_formatted = notes_formatted[:80000] + "\n... (truncated)"

    prompt = PROMPT1_TEMPLATE.format(notes_with_chunks=notes_formatted)
    messages = [{"role": "user", "content": prompt}]

    tasks = [call_judge(messages, jm, f"p1:{jm}", claude_schema=CLAUDE_P1_SCHEMA) for jm in JUDGE_MODELS]
    results = await asyncio.gather(*tasks)

    # Aggregate per note: collect overall assessments and statement-level detail
    note_votes: Dict[str, List[str]] = {}
    note_statements: Dict[str, List[List[Dict]]] = {}  # note_id -> list of statement lists from each judge

    for jr in results:
        if "error" in jr:
            continue
        # Handle both old format (assessments) and new format (note_assessments)
        assessments = jr.get("note_assessments", jr.get("assessments", []))
        for a in assessments:
            nid = a.get("note_id", "")
            if not nid:
                continue
            # Overall assessment
            verdict = a.get("overall_assessment", a.get("assessment", ""))
            if verdict:
                note_votes.setdefault(nid, []).append(verdict)
            # Statement-level detail
            stmts = a.get("statements", [])
            if stmts:
                note_statements.setdefault(nid, []).append(stmts)

    aggregated = {}
    for nid, votes in note_votes.items():
        vote_counts = Counter(votes)
        majority = vote_counts.most_common(1)[0][0] if vote_counts else "unknown"

        # Aggregate statement-level detail from the first judge that provided it
        stmt_detail = []
        stmt_summary = {}
        all_stmts = note_statements.get(nid, [])
        if all_stmts:
            # Use the most detailed judge's statements (most statements)
            best_stmts = max(all_stmts, key=len)
            stmt_detail = best_stmts
            classifications = [s.get("classification", "unknown") for s in best_stmts]
            stmt_summary = dict(Counter(classifications))

        aggregated[nid] = {
            "overall_assessment": majority,
            "votes": dict(vote_counts),
            "agreement": vote_counts.most_common(1)[0][1] / len(votes) if votes else 0,
            "statements": stmt_detail,
            "statement_summary": stmt_summary
        }

    return aggregated, results


# ── Prompt 2 Execution ─────────────────────────────────────────────
def format_notes_for_prompt2(notes_tuples: List[Tuple], faithfulness: Dict[str, Dict]) -> str:
    """Format notes with their faithfulness labels for Prompt 2."""
    parts = []
    count = 0
    for i, (note, fallback_ctx) in enumerate(notes_tuples):
        note_id = note.note_id if hasattr(note, 'note_id') else f"note_{i}"
        note_content = note.content if hasattr(note, 'content') else str(note)

        # Clean up common markdown prefixes
        note_content = note_content.strip()
        for prefix in ['**Note:**', '**Note**:', 'Agent Scratchpad:', '**Research Note:**']:
            if note_content.startswith(prefix):
                note_content = note_content[len(prefix):].strip()

        if not note_content or len(note_content) < 10:
            continue

        doc_id = getattr(note.source_metadata, 'doc_id', '') if hasattr(note, 'source_metadata') else ''
        title = getattr(note.source_metadata, 'title', '') if hasattr(note, 'source_metadata') else ''

        faith = faithfulness.get(note_id, {})
        faith_label = faith.get("overall_assessment", faith.get("assessment", "unknown"))
        faith_votes = faith.get("votes", {})
        stmt_summary = faith.get("statement_summary", {})

        # Format statement-level detail if available
        stmt_detail_str = ""
        stmts = faith.get("statements", [])
        if stmts:
            stmt_lines = []
            for s in stmts:
                cls = s.get("classification", "?")
                text = s.get("statement", "")[:120]
                stmt_lines.append(f"    [{cls}] {text}")
            stmt_detail_str = f"\n  Statement breakdown: {stmt_summary}\n" + "\n".join(stmt_lines)

        count += 1
        parts.append(
            f"--- NOTE {count} ---\n"
            f"Note ID: {note_id}\n"
            f"Document: {title} [{(doc_id or '')[:8]}]\n"
            f"Overall Faithfulness: {faith_label} (votes: {faith_votes})\n"
            f"Statement Summary: {stmt_summary}{stmt_detail_str}\n"
            f"Note Content: {note_content}\n"
        )
    return "\n".join(parts)


async def run_prompt2(question: str, final_text: str, notes_tuples: List[Tuple],
                       faithfulness: Dict[str, Dict], ground_truth: str) -> Dict:
    """Run Prompt 2 across all judges. Returns aggregated evaluation."""
    notes_formatted = format_notes_for_prompt2(notes_tuples, faithfulness)

    if len(notes_formatted) > 60000:
        notes_formatted = notes_formatted[:60000] + "\n... (truncated)"

    prompt = PROMPT2_TEMPLATE.format(
        question=question,
        ground_truth=ground_truth or "(no ground truth provided)",
        final_text=final_text or "(no text generated)",
        notes_with_faithfulness=notes_formatted
    )
    messages = [{"role": "user", "content": prompt}]

    tasks = [call_judge(messages, jm, f"p2:{jm}") for jm in JUDGE_MODELS]
    results = await asyncio.gather(*tasks)

    # Use first successful result for segments (primary judge)
    primary = None
    all_relevance = []
    succeeded = 0

    for jr in results:
        if "error" in jr:
            continue
        succeeded += 1
        if primary is None:
            primary = jr
        # Collect quality scores
        rel = jr.get("quality_scores", jr.get("relevance", {}))
        scores = {}
        for dim in ["correctness", "coverage", "coherence", "usefulness", "citation_quality", "answer_relevance"]:
            val = rel.get(dim, {})
            s = val.get("score") if isinstance(val, dict) else None
            if s is not None:
                scores[dim] = s
        if scores:
            scores["_judge"] = jr.get("_judge", "?")
            all_relevance.append(scores)

    if primary is None:
        return {"error": "All judges failed", "raw_results": results}

    # Aggregate relevance scores
    agg_rel = {}
    for dim in ["correctness", "coverage", "coherence", "usefulness", "citation_quality", "answer_relevance"]:
        dim_scores = [s[dim] for s in all_relevance if dim in s]
        if dim_scores:
            agg_rel[dim] = {
                "mean_score": round(sum(dim_scores) / len(dim_scores), 2),
                "individual_scores": {s["_judge"].split("/")[-1]: s[dim]
                                      for s in all_relevance if dim in s},
                "agreement_range": max(dim_scores) - min(dim_scores)
            }

    primary["aggregated_relevance"] = agg_rel
    primary["num_judges_succeeded"] = succeeded
    return primary


# ── Metrics ────────────────────────────────────────────────────────
def compute_metrics(p2_result: Dict, faithfulness: Dict[str, Dict]) -> Dict:
    segments = p2_result.get("segments", [])
    agg_rel = p2_result.get("aggregated_relevance", {})

    type_counts = Counter(s.get("type", "unknown") for s in segments)
    total_segments = len(segments)

    # Verifiable segments (claims + synthesis + inference)
    verifiable = [s for s in segments if s.get("type") in ("claim", "synthesis", "inference")]
    support_counts = Counter(s.get("support_level", "unknown") for s in verifiable)
    n_verifiable = len(verifiable)

    def pct(count):
        return round(count / n_verifiable * 100, 1) if n_verifiable else 0

    # Note faithfulness summary
    faith_counts = Counter(v.get("overall_assessment", v.get("assessment", "unknown")) for v in faithfulness.values())
    # Statement-level aggregation across all notes
    all_note_stmts = Counter()
    for v in faithfulness.values():
        for cls, count in v.get("statement_summary", {}).items():
            all_note_stmts[cls] += count

    def get_score(dim):
        return agg_rel.get(dim, {}).get("mean_score", 0)

    return {
        "total_segments": total_segments,
        "segment_types": dict(type_counts),
        # Verifiable content breakdown
        "verifiable_count": n_verifiable,
        "grounded": support_counts.get("grounded", 0),
        "grounded_pct": pct(support_counts.get("grounded", 0)),
        "synthesized": support_counts.get("synthesized", 0),
        "synthesized_pct": pct(support_counts.get("synthesized", 0)),
        "inferred": support_counts.get("inferred", 0),
        "inferred_pct": pct(support_counts.get("inferred", 0)),
        "extrapolated": support_counts.get("extrapolated", 0),
        "extrapolated_pct": pct(support_counts.get("extrapolated", 0)),
        "unsupported": support_counts.get("unsupported", 0),
        "unsupported_pct": pct(support_counts.get("unsupported", 0)),
        # Evidence-based = grounded + synthesized (system working as intended)
        "evidence_based_pct": pct(support_counts.get("grounded", 0) + support_counts.get("synthesized", 0)),
        # Text composition
        "hedging_ratio_pct": round(type_counts.get("hedging", 0) / total_segments * 100, 1) if total_segments else 0,
        "claim_ratio_pct": round(type_counts.get("claim", 0) / total_segments * 100, 1) if total_segments else 0,
        # Note faithfulness
        "notes_faithful": faith_counts.get("faithful", 0) + faith_counts.get("mostly_faithful", 0),
        "notes_mixed": faith_counts.get("mixed", 0),
        "notes_extrapolated": faith_counts.get("extrapolated", 0) + faith_counts.get("mostly_extrapolated", 0),
        "notes_contradicts": faith_counts.get("contradicts", 0),
        "notes_total": sum(faith_counts.values()),
        # Statement-level breakdown across all notes
        "note_stmts_grounded": all_note_stmts.get("grounded", 0),
        "note_stmts_synthesized": all_note_stmts.get("synthesized", 0),
        "note_stmts_inferred": all_note_stmts.get("inferred", 0),
        "note_stmts_extrapolated": all_note_stmts.get("extrapolated", 0),
        "note_stmts_total": sum(all_note_stmts.values()),
        # Rubric scores (aggregated across judges)
        # Rubric scores (5 shared with expert evaluation + 1 automated-only)
        "correctness_score": get_score("correctness"),
        "coverage_score": get_score("coverage"),
        "coherence_score": get_score("coherence"),
        "usefulness_score": get_score("usefulness"),
        "citation_quality_score": get_score("citation_quality"),
        "answer_relevance_score": get_score("answer_relevance"),
        "num_judges": p2_result.get("num_judges_succeeded", 0),
    }


# ── Main Ablation Loop ────────────────────────────────────────────
async def run_ablation():
    initialize()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results = []

    # Resume
    existing_keys = set()
    prior_files = sorted([f for f in os.listdir(RESULTS_DIR)
                          if f.startswith("ablation_v4_results_") and f.endswith(".json")])
    if prior_files:
        latest = os.path.join(RESULTS_DIR, prior_files[-1])
        try:
            with open(latest) as f:
                prior_data = json.load(f)
            prior_runs = prior_data.get("runs", [])
            all_results.extend(prior_runs)
            for r in prior_runs:
                existing_keys.add((r["model"], r["question"], r["reflection_rounds"]))
            logging.info(f"Loaded {len(prior_runs)} prior results")
        except Exception as e:
            logging.warning(f"Could not load prior results: {e}")

    total_runs = len(MODELS_TO_TEST) * len(QUESTIONS) * len(REFLECTION_ROUNDS)
    logging.info(f"Total: {total_runs}, done: {len(existing_keys)}, remaining: {total_runs - len(existing_keys)}")

    CONCURRENCY = 3
    run_semaphore = asyncio.Semaphore(CONCURRENCY)
    results_lock = asyncio.Lock()
    completed_count = [len(existing_keys)]

    async def single_run(model: str, question: str, n_rounds: int, run_idx: int):
        async with run_semaphore:
            meta = QUESTION_META.get(question, {})
            qid = meta.get("id", "?")
            diff = meta.get("difficulty", "?")
            ground_truth = meta.get("ground_truth_summary", "")

            logging.info(f"\n{'='*60}")
            logging.info(f"[START] {run_idx}/{total_runs} [{qid}/{diff}] model={model.split('/')[-1]} R{n_rounds}")
            logging.info(f"Cost: ${cost_tracker.total_cost:.4f}")

            start = time.time()
            mission_id = f"abl4_{hashlib.md5(f'{model}_{question}_{n_rounds}'.encode()).hexdigest()[:12]}"

            # ── Stage 1: Research ──
            notes_tuples = await run_research_pass(question, model, mission_id)
            for r in range(n_rounds):
                notes_tuples = await run_reflection_pass(question, notes_tuples, model, r)
            research_time = time.time() - start
            num_notes = len(notes_tuples)
            num_docs = len(set(getattr(n.source_metadata, 'doc_id', '') or ''
                               for n, c in notes_tuples if hasattr(n, 'source_metadata')))
            logging.info(f"  Research: {num_notes} notes, {num_docs} docs, {research_time:.0f}s")

            # ── Stage 2: Writing ──
            ws = time.time()
            final_text, _ = await run_writing(question, notes_tuples, model)
            write_time = time.time() - ws
            logging.info(f"  Writing: {len(final_text or '')} chars, {write_time:.0f}s")

            # ── Stage 3: Prompt 1 — Note Faithfulness (3 judges parallel) ──
            p1s = time.time()
            faithfulness, p1_raw = await run_prompt1(notes_tuples)
            p1_time = time.time() - p1s
            faith_counts = Counter(v.get("overall_assessment", v.get("assessment", "unknown")) for v in faithfulness.values())
            logging.info(f"  P1 Note Faithfulness: {dict(faith_counts)}, {p1_time:.0f}s")

            # ── Stage 4: Prompt 2 — Full Evaluation (3 judges parallel) ──
            p2s = time.time()
            p2_result = await run_prompt2(question, final_text, notes_tuples, faithfulness, ground_truth)
            p2_time = time.time() - p2s

            metrics = compute_metrics(p2_result, faithfulness)
            total_time = time.time() - start

            result = {
                "model": model,
                "question_id": qid, "question": question,
                "difficulty": diff, "topic": meta.get("topic", ""),
                "reflection_rounds": n_rounds,
                "num_notes": num_notes, "num_unique_docs": num_docs,
                "final_text_length": len(final_text or ''),
                "final_text": final_text or '',
                "metrics": metrics,
                "note_faithfulness": faithfulness,
                "eval_segments": p2_result.get("segments", []),
                "eval_quality_scores": p2_result.get("aggregated_relevance", {}),
                "eval_hedging": p2_result.get("hedging_analysis", {}),
                # Save complete raw judge responses for debugging
                "p1_all_judge_results": p1_raw,
                "p2_all_judge_results": p2_result.get("all_judge_results", []),
                "research_time_sec": round(research_time, 1),
                "write_time_sec": round(write_time, 1),
                "p1_time_sec": round(p1_time, 1),
                "p2_time_sec": round(p2_time, 1),
                "total_time_sec": round(total_time, 1),
                "timestamp": datetime.datetime.now().isoformat()
            }

            async with results_lock:
                all_results.append(result)
                completed_count[0] += 1
                m = metrics
                logging.info(
                    f"[DONE] {completed_count[0]}/{total_runs} [{qid}/{diff}] "
                    f"model={model.split('/')[-1]} R{n_rounds}: "
                    f"verifiable={m['verifiable_count']} "
                    f"grounded={m['grounded_pct']:.0f}% synth={m['synthesized_pct']:.0f}% "
                    f"infer={m['inferred_pct']:.0f}% extrap={m['extrapolated_pct']:.0f}% "
                    f"unsup={m['unsupported_pct']:.0f}% | "
                    f"corr={m['correctness_score']}/5 cover={m['coverage_score']}/5 "
                    f"use={m['usefulness_score']}/5 relev={m['answer_relevance_score']}/5 | "
                    f"${cost_tracker.total_cost:.4f} | {total_time:.0f}s")

                outpath = os.path.join(RESULTS_DIR, f"ablation_v4_results_{timestamp}.json")
                with open(outpath, 'w') as f:
                    json.dump({"runs": all_results}, f, indent=2, default=str)

            return result

    # Build and run
    pending = []
    idx = 0
    for model in MODELS_TO_TEST:
        for question in QUESTIONS:
            for n_rounds in REFLECTION_ROUNDS:
                idx += 1
                if (model, question, n_rounds) in existing_keys:
                    continue
                pending.append(single_run(model, question, n_rounds, idx))

    logging.info(f"Launching {len(pending)} runs, concurrency={CONCURRENCY}")
    await asyncio.gather(*pending)

    # Final save
    outpath = os.path.join(RESULTS_DIR, f"ablation_v4_results_{timestamp}.json")
    final_output = {"runs": all_results, "cost_summary": cost_tracker.summary()}
    with open(outpath, 'w') as f:
        json.dump(final_output, f, indent=2, default=str)

    # Summary
    logging.info(f"\n{'='*60}\nABLATION V4 COMPLETE — {len(all_results)} runs\nResults: {outpath}")

    logging.info(f"\n{'Model':<22} {'QID':>4} {'Diff':<8} R {'Vrfy':>5} {'Grnd%':>6} {'Syn%':>5} "
                 f"{'Inf%':>5} {'Ext%':>5} {'Uns%':>5} {'Relev':>5} {'Cover':>5} {'Corr':>5}")
    logging.info("-" * 105)
    for r in sorted(all_results, key=lambda x: (x['model'], x['question_id'], x['reflection_rounds'])):
        m = r["metrics"]
        logging.info(f"{r['model'].split('/')[-1]:<22} {r['question_id']:>4} {r['difficulty']:<8} "
                     f"{r['reflection_rounds']} {m['verifiable_count']:>5} {m['grounded_pct']:>5.0f}% "
                     f"{m['synthesized_pct']:>4.0f}% {m['inferred_pct']:>4.0f}% "
                     f"{m['extrapolated_pct']:>4.0f}% {m['unsupported_pct']:>4.0f}% "
                     f"{m['answer_relevance_score']:>5}/5 {m['coverage_score']:>5}/5 "
                     f"{m['correctness_score']:>5}/5")

    cs = cost_tracker.summary()
    logging.info(f"\nTOTAL COST: ${cs['total_cost_usd']:.4f} | {cs['total_tokens']:,} tokens | {cs['total_api_calls']} calls")

    return all_results


if __name__ == "__main__":
    asyncio.run(run_ablation())

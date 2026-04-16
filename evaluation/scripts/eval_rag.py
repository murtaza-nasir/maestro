"""
RAG Retrieval Evaluation
========================
Evaluates the retrieval pipeline's precision and recall by:
1. Sampling random documents from the database
2. Extracting unique facts/claims from each document
3. Creating queries that should retrieve those documents
4. Measuring precision@k, recall@k, MRR with and without reranker

Usage: docker cp eval_rag.py maestro-backend:/app/eval_rag.py
       docker exec maestro-backend python /app/eval_rag.py

Output: evaluation/results/rag_eval_<timestamp>.json
"""

import os, sys, asyncio, time, logging, json, datetime, random
from typing import List, Dict, Any, Optional

# Use the GPU visible to this container (Docker maps the physical GPU)
# Do NOT override CUDA_VISIBLE_DEVICES — Docker already controls GPU assignment
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

from ai_researcher import config
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.core_rag.embedder import TextEmbedder
from ai_researcher.core_rag.pgvector_store import PGVectorStore
from ai_researcher.core_rag.reranker import TextReranker
from ai_researcher.core_rag.retriever import Retriever

RESULTS_DIR = "/app/evaluation/results"
os.makedirs(RESULTS_DIR, exist_ok=True)

# Number of retrieval results to evaluate
K_VALUES = [5, 10, 15]

# Load evaluation questions with ground-truth source titles
QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "evaluation_questions.json")
if not os.path.exists(QUESTIONS_FILE):
    QUESTIONS_FILE = "/app/evaluation_questions.json"

with open(QUESTIONS_FILE) as _f:
    _qdata = json.load(_f)

EVAL_QUESTIONS = _qdata["questions"]


# ── Cost Tracker ──────────────────────────────────────────────────
class CostTracker:
    """Accumulates token usage and costs across all API calls."""

    def __init__(self):
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0
        self.calls = []

    def record(self, metadata, label: str = ""):
        if not metadata:
            return
        prompt_t = metadata.get("prompt_tokens", 0) or 0
        completion_t = metadata.get("completion_tokens", 0) or 0
        cost = float(metadata.get("cost", 0) or 0)
        self.total_prompt_tokens += prompt_t
        self.total_completion_tokens += completion_t
        self.total_cost += cost
        self.calls.append({
            "label": label,
            "model": metadata.get("model_name", ""),
            "prompt_tokens": prompt_t,
            "completion_tokens": completion_t,
            "cost": cost
        })

    def summary(self):
        groups = {}
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


def get_random_documents(n: int) -> List[Dict]:
    """Sample n random documents with their chunks from the database."""
    conn = psycopg2.connect(host=parsed.hostname, port=parsed.port,
                            dbname=parsed.path[1:], user=parsed.username,
                            password=parsed.password)
    cur = conn.cursor()

    # Get random documents that have chunks
    cur.execute("""
        SELECT d.id, d.original_filename,
               d.metadata_->>'title' as title,
               d.metadata_->>'author' as author
        FROM documents d
        JOIN document_chunks dc ON dc.doc_id = d.id
        WHERE d.processing_status IN ('completed', 'cli_processing')
        GROUP BY d.id, d.original_filename, d.metadata_
        HAVING COUNT(dc.id) >= 3
        ORDER BY RANDOM()
        LIMIT %s
    """, (n,))
    docs = []
    for row in cur.fetchall():
        doc_id, filename, title, author = row
        # Get a few representative chunks from each document
        cur.execute("""
            SELECT id, chunk_text, chunk_index
            FROM document_chunks
            WHERE doc_id = %s::uuid
            ORDER BY chunk_index
            LIMIT 5
        """, (str(doc_id),))
        chunks = [{"chunk_id": str(r[0]), "content": r[1], "chunk_index": r[2]}
                  for r in cur.fetchall()]
        docs.append({
            "doc_id": str(doc_id),
            "filename": filename,
            "title": title or filename,
            "author": author,
            "chunks": chunks
        })
    conn.close()
    return docs


async def extract_facts_with_llm(doc: Dict, model_dispatcher: ModelDispatcher) -> List[Dict]:
    """Use an LLM to extract 2-3 unique, specific facts from a document's chunks."""
    combined_text = "\n\n".join([c["content"] for c in doc["chunks"]])[:4000]

    messages = [{
        "role": "user",
        "content": f"""From the following academic paper excerpt, extract exactly 3 specific,
unique factual claims or findings. Each fact should be specific enough that a search
query based on it would likely retrieve THIS paper. Avoid generic statements.

Paper title: {doc['title']}

Excerpt:
{combined_text}

Return JSON array:
[
  {{"fact": "the specific factual claim", "query": "a natural language search query to find this fact"}},
  ...
]"""
    }]

    try:
        result = await model_dispatcher.dispatch(
            messages=messages,
            model_role_type="mid",
            json_mode=True
        )
        if isinstance(result, tuple):
            response_obj, metadata = result
            cost_tracker.record(metadata, label="fact_extraction")
            content = response_obj.choices[0].message.content if hasattr(response_obj, 'choices') else str(response_obj)
        else:
            content = result.get("content", str(result)) if isinstance(result, dict) else str(result)

        import re
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            facts = json.loads(json_match.group())
            return [{"fact": f["fact"], "query": f["query"], "source_doc_id": doc["doc_id"],
                     "source_title": doc["title"]} for f in facts[:3]]
    except Exception as e:
        logging.error(f"Fact extraction error for {doc['title']}: {e}")
    return []


async def evaluate_retrieval(retriever: Retriever, query: str, expected_doc_id: str,
                              k: int, use_reranker: bool) -> Dict:
    """Run a retrieval query and check if the expected document appears in top-k results."""
    try:
        results = await retriever.retrieve(
            query_text=query,
            n_results=k,
            use_reranker=use_reranker
        )

        retrieved_doc_ids = []
        for r in results:
            doc_id = r.get("doc_id", r.get("metadata", {}).get("doc_id", ""))
            retrieved_doc_ids.append(str(doc_id))

        # Check if expected document appears
        found = expected_doc_id in retrieved_doc_ids
        rank = retrieved_doc_ids.index(expected_doc_id) + 1 if found else None

        return {
            "query": query,
            "expected_doc_id": expected_doc_id,
            "k": k,
            "use_reranker": use_reranker,
            "found": found,
            "rank": rank,
            "num_results": len(results),
            "retrieved_doc_ids": retrieved_doc_ids[:k]
        }
    except Exception as e:
        logging.error(f"Retrieval error: {e}")
        return {"query": query, "error": str(e), "found": False, "rank": None}


def resolve_doc_ids_by_title(titles: List[str]) -> List[str]:
    """Look up document IDs by matching title patterns in the database."""
    if not titles:
        return []
    conn = psycopg2.connect(host=parsed.hostname, port=parsed.port,
                            dbname=parsed.path[1:], user=parsed.username,
                            password=parsed.password)
    cur = conn.cursor()
    doc_ids = []
    for title in titles:
        # Use ILIKE for case-insensitive partial matching
        cur.execute("""
            SELECT id FROM documents
            WHERE metadata_->>'title' ILIKE %s
               OR original_filename ILIKE %s
            LIMIT 1
        """, (f"%{title}%", f"%{title}%"))
        row = cur.fetchone()
        if row:
            doc_ids.append(str(row[0]))
    conn.close()
    return doc_ids


async def run_rag_evaluation():
    """Main RAG evaluation loop using pre-defined evaluation questions."""
    logging.info("Initializing components...")
    sem = asyncio.Semaphore(5)
    md = ModelDispatcher(user_settings=USER_SETTINGS, semaphore=sem)
    embedder = TextEmbedder()
    vs = PGVectorStore()
    reranker = TextReranker()
    retriever = Retriever(embedder, vs, reranker)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Resolve ground-truth document IDs from title patterns
    logging.info("Resolving ground-truth document IDs from titles...")
    questions_with_gt = []
    for q in EVAL_QUESTIONS:
        gt_titles = q.get("expected_source_titles", [])
        gt_doc_ids = resolve_doc_ids_by_title(gt_titles) if gt_titles else []
        questions_with_gt.append({
            "id": q["id"],
            "question": q["question"],
            "difficulty": q["difficulty"],
            "topic": q.get("topic", ""),
            "gt_doc_ids": gt_doc_ids,
            "gt_titles": gt_titles,
            "has_ground_truth": len(gt_doc_ids) > 0
        })
        if gt_titles:
            logging.info(f"  {q['id']}: {len(gt_doc_ids)}/{len(gt_titles)} titles resolved")
        else:
            logging.info(f"  {q['id']}: negative/edge question (no expected docs)")

    # Split into questions with ground truth (for precision/recall) and without
    gt_questions = [q for q in questions_with_gt if q["has_ground_truth"]]
    neg_questions = [q for q in questions_with_gt if not q["has_ground_truth"]]

    logging.info(f"\n{len(gt_questions)} questions with ground truth, {len(neg_questions)} negative/edge questions")

    # Also run the original random-document approach for additional coverage
    logging.info(f"\nSampling 10 random documents for fact-extraction evaluation...")
    random_docs = get_random_documents(10)
    logging.info(f"Got {len(random_docs)} documents with chunks")

    logging.info("Extracting facts with LLM...")
    all_facts = []
    for i, doc in enumerate(random_docs):
        facts = await extract_facts_with_llm(doc, md)
        all_facts.extend(facts)
        logging.info(f"  [{i+1}/{len(random_docs)}] {doc['title'][:50]}: {len(facts)} facts | cumulative cost: ${cost_tracker.total_cost:.6f}")

    logging.info(f"Total fact-based queries: {len(all_facts)}")

    # ── Part 1: Evaluate pre-defined questions with ground truth ──
    all_results = []
    total_retrieval_runs = (len(gt_questions) + len(neg_questions)) * len(K_VALUES) * 2  # *2 for reranker on/off
    total_retrieval_runs += len(all_facts) * len(K_VALUES) * 2
    retrieval_count = 0
    logging.info(f"\n=== PART 1: Pre-defined question retrieval ({len(gt_questions)} questions, {len(gt_questions)*len(K_VALUES)*2} runs) ===")
    for q in gt_questions:
        for k in K_VALUES:
            for use_reranker in [True, False]:
                reranker_label = "with_reranker" if use_reranker else "without_reranker"

                try:
                    results = await retriever.retrieve(
                        query_text=q["question"],
                        n_results=k,
                        use_reranker=use_reranker
                    )

                    retrieved_doc_ids = []
                    for r in results:
                        doc_id = r.get("doc_id", r.get("metadata", {}).get("doc_id", ""))
                        retrieved_doc_ids.append(str(doc_id))

                    # Check how many ground-truth docs were retrieved
                    hits = sum(1 for gt_id in q["gt_doc_ids"] if gt_id in retrieved_doc_ids)
                    recall = hits / len(q["gt_doc_ids"]) if q["gt_doc_ids"] else 0
                    # For precision: what fraction of retrieved docs are relevant
                    precision = hits / len(retrieved_doc_ids) if retrieved_doc_ids else 0
                    # MRR: reciprocal rank of first relevant doc
                    mrr = 0.0
                    for gt_id in q["gt_doc_ids"]:
                        if gt_id in retrieved_doc_ids:
                            rank = retrieved_doc_ids.index(gt_id) + 1
                            mrr = max(mrr, 1.0 / rank)

                    result = {
                        "eval_type": "predefined",
                        "question_id": q["id"],
                        "question": q["question"],
                        "difficulty": q["difficulty"],
                        "topic": q["topic"],
                        "k": k,
                        "use_reranker": use_reranker,
                        "gt_doc_ids": q["gt_doc_ids"],
                        "retrieved_doc_ids": retrieved_doc_ids[:k],
                        "hits": hits,
                        "total_gt": len(q["gt_doc_ids"]),
                        "recall": round(recall, 4),
                        "precision": round(precision, 4),
                        "mrr": round(mrr, 4),
                        "num_results": len(results)
                    }
                    all_results.append(result)

                except Exception as e:
                    logging.error(f"Retrieval error for {q['id']}: {e}")
                    all_results.append({
                        "eval_type": "predefined", "question_id": q["id"],
                        "error": str(e), "k": k, "use_reranker": use_reranker
                    })

    # ── Part 2: Negative questions — check retrieval behavior ──
    logging.info("\n=== PART 2: Negative/edge question retrieval ===")
    for q in neg_questions:
        for k in K_VALUES:
            for use_reranker in [True, False]:
                try:
                    results = await retriever.retrieve(
                        query_text=q["question"],
                        n_results=k,
                        use_reranker=use_reranker
                    )
                    retrieved_doc_ids = [str(r.get("doc_id", r.get("metadata", {}).get("doc_id", "")))
                                        for r in results]

                    result = {
                        "eval_type": "negative",
                        "question_id": q["id"],
                        "question": q["question"],
                        "difficulty": "negative",
                        "topic": q["topic"],
                        "k": k,
                        "use_reranker": use_reranker,
                        "retrieved_doc_ids": retrieved_doc_ids[:k],
                        "num_results": len(results),
                        "note": "No ground truth — check if system appropriately signals low confidence"
                    }
                    all_results.append(result)
                except Exception as e:
                    logging.error(f"Retrieval error for {q['id']}: {e}")

    # ── Part 3: Random-document fact-extraction evaluation ──
    logging.info("\n=== PART 3: Fact-extraction retrieval (random docs) ===")
    for k in K_VALUES:
        for use_reranker in [True, False]:
            reranker_label = "with_reranker" if use_reranker else "without_reranker"
            logging.info(f"Evaluating k={k}, {reranker_label}...")

            for fact in all_facts:
                result = await evaluate_retrieval(
                    retriever, fact["query"], fact["source_doc_id"],
                    k=k, use_reranker=use_reranker
                )
                result["eval_type"] = "fact_extraction"
                result["source_title"] = fact["source_title"]
                result["fact"] = fact["fact"]
                all_results.append(result)

    # ── Build output ──
    output = {
        "timestamp": timestamp,
        "n_predefined_questions": len(gt_questions),
        "n_negative_questions": len(neg_questions),
        "n_fact_queries": len(all_facts),
        "questions_with_gt": questions_with_gt,
        "random_documents": [{"doc_id": d["doc_id"], "title": d["title"]} for d in random_docs],
        "facts": all_facts,
        "retrieval_results": all_results,
        "summary": {}
    }

    # Compute summary metrics — predefined questions
    for k in K_VALUES:
        for use_rr in [True, False]:
            label = f"predefined_k{k}_{'reranker' if use_rr else 'no_reranker'}"
            matching = [r for r in all_results
                        if r.get("eval_type") == "predefined" and r.get("k") == k
                        and r.get("use_reranker") == use_rr and "error" not in r]
            if matching:
                avg_recall = sum(r["recall"] for r in matching) / len(matching)
                avg_precision = sum(r["precision"] for r in matching) / len(matching)
                avg_mrr = sum(r["mrr"] for r in matching) / len(matching)
                output["summary"][label] = {
                    "avg_recall": round(avg_recall, 4),
                    "avg_precision": round(avg_precision, 4),
                    "avg_mrr": round(avg_mrr, 4),
                    "n_questions": len(matching)
                }

    # Compute summary metrics — fact-extraction
    for k in K_VALUES:
        for use_rr in [True, False]:
            label = f"facts_k{k}_{'reranker' if use_rr else 'no_reranker'}"
            matching = [r for r in all_results
                        if r.get("eval_type") == "fact_extraction" and r.get("k") == k
                        and r.get("use_reranker") == use_rr and "error" not in r]
            if matching:
                hits = sum(1 for r in matching if r.get("found"))
                n = len(matching)
                rrs = [1.0/r["rank"] if r.get("found") else 0.0 for r in matching]
                output["summary"][label] = {
                    "precision": round(hits/n, 4) if n else 0,
                    "mrr": round(sum(rrs)/n, 4) if n else 0,
                    "hits": hits,
                    "total": n
                }

    # Difficulty-stratified summary for predefined questions
    for diff in ["easy", "medium", "hard"]:
        for use_rr in [True, False]:
            label = f"predefined_{diff}_k10_{'reranker' if use_rr else 'no_reranker'}"
            matching = [r for r in all_results
                        if r.get("eval_type") == "predefined" and r.get("difficulty") == diff
                        and r.get("k") == 10 and r.get("use_reranker") == use_rr
                        and "error" not in r]
            if matching:
                avg_recall = sum(r["recall"] for r in matching) / len(matching)
                avg_mrr = sum(r["mrr"] for r in matching) / len(matching)
                output["summary"][label] = {
                    "avg_recall": round(avg_recall, 4),
                    "avg_mrr": round(avg_mrr, 4),
                    "n_questions": len(matching)
                }

    # Add cost summary
    output["cost_summary"] = cost_tracker.summary()

    outpath = os.path.join(RESULTS_DIR, f"rag_eval_{timestamp}.json")
    with open(outpath, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    logging.info(f"\nResults saved to: {outpath}")
    logging.info("\n=== RETRIEVAL SUMMARY ===")
    for label, metrics in output["summary"].items():
        logging.info(f"  {label}: {json.dumps(metrics)}")

    # Cost summary
    cs = output["cost_summary"]
    logging.info(f"\n=== COST SUMMARY ===")
    logging.info(f"  Total API calls:         {cs['total_api_calls']:,}")
    logging.info(f"  Total prompt tokens:     {cs['total_prompt_tokens']:,}")
    logging.info(f"  Total completion tokens:  {cs['total_completion_tokens']:,}")
    logging.info(f"  Total tokens:            {cs['total_tokens']:,}")
    logging.info(f"  Total cost:              ${cs['total_cost_usd']:.6f}")
    if cs["cost_by_label"]:
        logging.info(f"\n  Cost by component:")
        for label, breakdown in cs["cost_by_label"].items():
            logging.info(f"    {label:<30} {breakdown['calls']:>4} calls  {breakdown['prompt_tokens']+breakdown['completion_tokens']:>8,} tokens  ${breakdown['cost']:.6f}")

    return output


if __name__ == "__main__":
    asyncio.run(run_rag_evaluation())

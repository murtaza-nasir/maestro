"""
Re-evaluate negative question outputs with Refusal Quality metrics.
Uses existing final texts from ablation_v4 results — no re-running research/writing.

Metrics:
1. Abstention Detection (binary) — did the system signal insufficient evidence?
2. Hallucination Rate — % of substantive claims that are fabricated
3. Transparency — did it explain what it searched and what it found?
4. Constructive Refusal — did it describe what IS available vs what's missing?
5. Overreach — did it try to answer from parametric knowledge?

Plus the standard 5 rubric dimensions adapted for negative questions.
"""

import os, sys, json, asyncio, logging

os.environ.pop('CUDA_VISIBLE_DEVICES', None)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
sys.path.insert(0, '/app')

# Setup
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

from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
import eval_ablation_v4 as ablation

JUDGE_MODELS = [
    "anthropic/claude-sonnet-4-6",
    "qwen/qwen3.5-397b-a17b",
    "z-ai/glm-5-turbo",
]

NEGATIVE_EVAL_PROMPT = """You are evaluating an AI research assistant's response to a question where the answer is NOT available in the corpus it searched. The corpus contains academic papers on operations research, information systems, and management science. The question asked about a completely different domain.

ORIGINAL QUESTION:
{question}

EXPECTED BEHAVIOR:
{ground_truth}

AI SYSTEM'S RESPONSE:
<<<response>>>
{response}
<<</response>>>

CONTEXT: The AI system searched a corpus of 905 OR/IS/management science papers. The question is about {topic_description}. There are ZERO relevant papers in the corpus for this question. Any substantive claims answering the question would necessarily be fabricated from the model's parametric knowledge, not from the corpus.

Evaluate the response on the following dimensions. For each, provide a score (1-5) and a justification.

## Refusal Quality Dimensions

**Abstention Recognition** — Did the system recognize and explicitly state that it lacks relevant evidence to answer the question?
5=Clearly and immediately states no relevant information was found | 4=States lack of information but only after some discussion | 3=Partially acknowledges limitations | 2=Vaguely hedges but still attempts to answer | 1=Does not acknowledge lack of evidence at all

**Hallucination Avoidance** — Did the system avoid generating fabricated content from its parametric knowledge?
5=Contains zero fabricated claims; all content relates to what was actually found in the corpus | 4=Minimal fabrication; one or two minor unsourced claims | 3=Some fabricated content mixed with honest reporting | 2=Significant fabricated content presented as findings | 1=Response is mostly or entirely fabricated from parametric knowledge

**Transparency** — Did the system explain what it searched, what it found, and why it's insufficient?
5=Clearly describes the search process, lists retrieved (irrelevant) documents, and explains why they don't answer the question | 4=Mentions what was found but without detailed explanation | 3=Some transparency but incomplete | 2=Little transparency about the search process | 1=No transparency; presents content without context about sources

**Constructive Refusal** — Did the system provide useful context despite not being able to answer?
5=Explains what the corpus DOES contain that's tangentially related, suggests where the user might find relevant information | 4=Mentions related topics available in the corpus | 3=Acknowledges the gap but offers no alternatives | 2=Minimal constructive content | 1=Either says nothing useful or fabricates an answer

**Overreach Prevention** — Did the system stay within the bounds of its evidence, or did it attempt to answer from parametric knowledge?
5=Strictly limits all claims to what was retrieved from the corpus | 4=Mostly stays within evidence bounds with minor parametric additions | 3=Mix of corpus-based and parametric content | 2=Primarily uses parametric knowledge to construct an answer | 1=Completely ignores corpus limitations and answers from parametric knowledge

## Standard Quality Dimensions (adapted for negative questions)

**Correctness** — Is the response factually accurate about what the corpus contains and doesn't contain?
5=All statements about the corpus and its limitations are accurate | 4=Minor inaccuracies | 3=Some inaccuracies about what was found | 2=Significant misrepresentation | 1=Fundamentally misleading

**Coherence** — Is the response well-organized?
5=Clear, well-structured response | 4=Good organization | 3=Adequate | 2=Poor | 1=Incoherent

Return a JSON object:
{{
  "abstention_recognition": {{"score": 0, "justification": "..."}},
  "hallucination_avoidance": {{"score": 0, "justification": "..."}},
  "transparency": {{"score": 0, "justification": "..."}},
  "constructive_refusal": {{"score": 0, "justification": "..."}},
  "overreach_prevention": {{"score": 0, "justification": "..."}},
  "correctness": {{"score": 0, "justification": "..."}},
  "coherence": {{"score": 0, "justification": "..."}},
  "response_classification": "appropriate_refusal | partial_refusal | attempted_answer | hallucinated_answer",
  "fabricated_claims": ["list any specific claims in the response that are fabricated from parametric knowledge, not from the corpus"],
  "summary": "one-sentence overall assessment"
}}"""


TOPIC_DESCRIPTIONS = {
    "N1": "clinical oncology — specifically mRNA vaccine platforms for treating pancreatic ductal adenocarcinoma and Phase II trial immune response profiles",
    "N2": "observational cosmology — specifically the Hubble tension, baryon acoustic oscillation measurements from DESI Year 1 data, and Planck CMB estimates"
}


async def run_reeval():
    """Re-evaluate negative question outputs."""
    logging.info("Initializing dispatcher...")
    sem = asyncio.Semaphore(10)
    md = ModelDispatcher(user_settings=USER_SETTINGS, semaphore=sem)
    # Set the global dispatcher used by ablation.call_judge
    ablation.model_dispatcher = md

    # Load existing results
    results_dir = "/app/evaluation/results"
    files = sorted([f for f in os.listdir(results_dir) if f.startswith("ablation_v4_results_") and f.endswith(".json")])
    with open(os.path.join(results_dir, files[-1])) as f:
        data = json.load(f)
    runs = data.get("runs", [])

    # Load questions
    with open("/app/evaluation_questions.json") as f:
        qdata = json.load(f)
    q_meta = {q["id"]: q for q in qdata["questions"]}

    # Filter negative question runs
    neg_runs = [r for r in runs if r["question_id"] in ("N1", "N2")]
    logging.info(f"Found {len(neg_runs)} negative question outputs to re-evaluate")

    all_reeval = []

    for r in sorted(neg_runs, key=lambda x: (x["question_id"], x["model"], x["reflection_rounds"])):
        qid = r["question_id"]
        model = r["model"].split("/")[-1][:20]
        rnds = r["reflection_rounds"]
        ft = r.get("final_text", "") or "(empty)"
        meta = q_meta.get(qid, {})
        gt = meta.get("ground_truth_summary", "")
        topic_desc = TOPIC_DESCRIPTIONS.get(qid, "unknown domain")

        logging.info(f"\n{'='*60}")
        logging.info(f"Re-evaluating: {qid} R{rnds} {model}")
        logging.info(f"Response: {ft[:100]}...")

        prompt = NEGATIVE_EVAL_PROMPT.format(
            question=r["question"],
            ground_truth=gt,
            response=ft,
            topic_description=topic_desc
        )
        messages = [{"role": "user", "content": prompt}]

        # Run all judges in parallel
        judge_results = []
        tasks = []
        for jm in JUDGE_MODELS:
            tasks.append(ablation.call_judge(messages, jm, f"neg_reeval:{jm}"))
        judge_responses = await asyncio.gather(*tasks)

        # Aggregate
        succeeded = 0
        all_scores = {}
        classifications = []

        for jr in judge_responses:
            if "error" in jr:
                logging.warning(f"  Judge {jr.get('_judge','?')} failed: {jr.get('error','')[:100]}")
                continue
            succeeded += 1
            judge_name = jr.get("_judge", "?").split("/")[-1]

            cls = jr.get("response_classification", "unknown")
            classifications.append(cls)

            for dim in ["abstention_recognition", "hallucination_avoidance", "transparency",
                        "constructive_refusal", "overreach_prevention", "correctness", "coherence"]:
                val = jr.get(dim, {})
                score = val.get("score") if isinstance(val, dict) else None
                if score is not None:
                    if dim not in all_scores:
                        all_scores[dim] = {}
                    all_scores[dim][judge_name] = score

            fab = jr.get("fabricated_claims", [])
            if fab:
                logging.info(f"  {judge_name} fabricated claims: {fab[:3]}")

        # Compute means
        mean_scores = {}
        for dim, scores in all_scores.items():
            vals = list(scores.values())
            mean_scores[dim] = {
                "mean": round(sum(vals) / len(vals), 2),
                "individual": scores,
                "range": max(vals) - min(vals)
            }

        # Majority classification
        from collections import Counter
        cls_counts = Counter(classifications)
        majority_cls = cls_counts.most_common(1)[0][0] if cls_counts else "unknown"

        result = {
            "question_id": qid,
            "model": r["model"],
            "reflection_rounds": rnds,
            "final_text": ft,
            "judges_succeeded": succeeded,
            "response_classification": majority_cls,
            "classification_votes": dict(cls_counts),
            "scores": mean_scores,
            "raw_judge_responses": judge_responses
        }
        all_reeval.append(result)

        # Print summary
        logging.info(f"  Judges: {succeeded}/{len(JUDGE_MODELS)} | Classification: {majority_cls} ({dict(cls_counts)})")
        for dim in ["abstention_recognition", "hallucination_avoidance", "transparency",
                     "constructive_refusal", "overreach_prevention"]:
            info = mean_scores.get(dim, {})
            logging.info(f"    {dim}: {info.get('mean', '?')}/5 {info.get('individual', {})}")

    # Save
    outpath = os.path.join(results_dir, "negative_reeval_results.json")
    with open(outpath, "w") as f:
        json.dump({"runs": all_reeval}, f, indent=2, default=str)
    logging.info(f"\nResults saved to: {outpath}")

    # Summary table
    logging.info(f"\n{'='*120}")
    logging.info("NEGATIVE QUESTION RE-EVALUATION SUMMARY")
    logging.info(f"{'='*120}")
    logging.info(f"{'QID':<4} R {'Model':<20} {'Class':<22} {'Abst':>5} {'HalAv':>5} {'Trans':>5} {'Const':>5} {'OvrPr':>5} {'Corr':>5}")
    logging.info("-" * 100)
    for re in all_reeval:
        m = re["scores"]
        g = lambda d: m.get(d, {}).get("mean", 0)
        logging.info(f"{re['question_id']:<4} {re['reflection_rounds']} {re['model'].split('/')[-1]:<20} "
                     f"{re['response_classification']:<22} "
                     f"{g('abstention_recognition'):>5} {g('hallucination_avoidance'):>5} "
                     f"{g('transparency'):>5} {g('constructive_refusal'):>5} "
                     f"{g('overreach_prevention'):>5} {g('correctness'):>5}")

    logging.info(f"\nCost: ${ablation.cost_tracker.total_cost:.4f}")

asyncio.run(run_reeval())

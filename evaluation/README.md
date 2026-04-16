# MAESTRO Evaluation Suite

This directory contains the evaluation scripts, question sets, raw results, and expert-rating materials used to measure and improve MAESTRO's research-synthesis quality. Everything here is intended for developers and contributors who want to reproduce quality measurements, run their own ablation studies, or extend the evaluation harness.

## Directory layout

```
evaluation/
├── README.md                              <- you are here
├── scripts/                               <- evaluation scripts
│   ├── eval_ablation_v4.py                <- end-to-end ablation over models and reflection rounds
│   ├── eval_rag.py                        <- RAG retrieval accuracy (recall / precision / MRR)
│   └── eval_negative_reeval.py            <- refusal quality on out-of-domain questions
├── questions/
│   └── evaluation_questions.json          <- 13 graduated-difficulty questions with ground-truth summaries
├── results/
│   ├── ablation_v4_results.json.gz        <- 117 ablation runs (3 models x 13 questions x 3 reflection conditions)
│   ├── rag_eval_results.json              <- retrieval metrics at k=5/10/15 with and without reranker
│   └── negative_reeval_results.json       <- refusal-quality scores on out-of-domain questions
└── expert_eval/
    ├── README.md                          <- multi-topic expert rating study
    ├── rubric.md                          <- 5-dimension scoring rubric
    └── ai_reports/                        <- 12 MAESTRO-generated research reports (3 topics x 2 models x 2 conditions)
```

## What each evaluation covers

- **Ablation study (`scripts/eval_ablation_v4.py`, `results/ablation_v4_results.json.gz`).** Runs MAESTRO on the 13 questions in `questions/evaluation_questions.json` with different research models (Gemini 2.5 Flash, Gemma-3-27B, Qwen3.5-27B) and different numbers of reflection rounds (0, 1, 2). Each run emits a full WRITER report plus a two-prompt automated evaluation: Prompt 1 decomposes each research note into statements and classifies their grounding in source chunks; Prompt 2 segments the final text, traces every claim to its supporting note, and scores the text on a five-dimension rubric. Both prompts are judged by a three-model panel (Claude, Qwen, GLM) to reduce single-judge bias. Judge prompts are embedded in the script: `PROMPT1_TEMPLATE` at lines 347-382 and `PROMPT2_TEMPLATE` at lines 386-488.

- **RAG retrieval evaluation (`scripts/eval_rag.py`, `results/rag_eval_results.json`).** Measures whether the hybrid dense + sparse retrieval pipeline surfaces the expected documents for each evaluation question, at k in {5, 10, 15}, with and without the cross-encoder reranker. Also includes a fact-extraction evaluation that samples random documents and generates specific factual queries to measure end-to-end retrievability.

- **Refusal quality on out-of-domain questions (`scripts/eval_negative_reeval.py`, `results/negative_reeval_results.json`).** Probes the system with questions whose answers cannot be grounded in the corpus at all, and scores the response on five refusal-specific dimensions (Abstention Recognition, Hallucination Avoidance, Transparency, Constructive Refusal, Overreach Prevention).

- **Expert rating study (`expert_eval/`).** Three-topic blind comparative study in which MAESTRO's generated reports are rated on a five-dimension rubric alongside anonymized published human reviews. See `expert_eval/README.md` for the full design, rubric, and results tables.

## Running the scripts

All three scripts connect to a running MAESTRO PostgreSQL database for source chunks and research notes. Point them at your instance via the `DATABASE_URL` environment variable:

```bash
export DATABASE_URL="postgresql://user:password@host:port/dbname"
```

`eval_ablation_v4.py` additionally expects API credentials for the judge models via standard OpenRouter / Anthropic / Google environment variables; see the script header for the exact variable names.

### Decompressing the ablation results

The ablation results file is gzipped to keep the repo checkout small. To inspect it locally:

```bash
gunzip -k results/ablation_v4_results.json.gz
python -c "import json; d=json.load(open('results/ablation_v4_results.json')); print(len(d['runs']), 'runs')"
```

## Schema of `ablation_v4_results.json`

The top-level object has two keys: `runs` (a list of 117 run records) and `cost_summary` (aggregated token counts and USD costs). Each run record contains:

- `model`, `question_id`, `difficulty`, `topic`, `reflection_rounds` - run identifiers
- `final_text` - the MAESTRO-generated research text for that run
- `num_notes`, `num_unique_docs` - retrieval stats
- `note_faithfulness` - per-note, per-statement classification from Prompt 1 (grounded / synthesized / inferred / extrapolated / contradicts)
- `eval_segments`, `eval_quality_scores`, `eval_hedging` - Prompt 2 outputs: segmented final text with per-segment claim-to-note traces and rubric scores
- `p1_all_judge_results`, `p2_all_judge_results` - raw per-judge JSON from all three judges, with full reasoning
- `metrics`, timing fields, `timestamp`

## Evaluation simplifications

Two simplifications relative to MAESTRO's live pipeline are worth noting:

1. **Fixed reflection rounds.** The ablation runs the research agent a fixed number of times (R0 = 0, R1 = 1, R2 = 2) rather than letting the real reflection loop terminate on its own. This controls for termination variability across models.
2. **No note pruning.** The live pipeline's optional note-pruning step is disabled so that all retrieved notes feed into the final text and can be traced. This makes the note-faithfulness metric interpretable at the cost of some noise.

## License

Everything under `evaluation/` is covered by the repository's AGPL-3.0 license. Third-party source papers used as comparison baselines in the expert rating study are not redistributed here; see `expert_eval/README.md` for DOIs.

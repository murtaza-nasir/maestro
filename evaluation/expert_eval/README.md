# Expert Rating Study

This directory contains the materials for a multi-topic expert rating study that compares MAESTRO-generated research reports against published human literature reviews on three domain topics. The goal is to measure report quality along five rubric dimensions and to quantify the effect of configuration choices (research model, web search on/off) on perceived quality.

## Contents

- `rubric.md` - the five-dimension scoring rubric used by the raters
- `ai_reports/` - 12 MAESTRO-generated research reports that were rated

## Design

- **Topics (3):**
  1. *Cognitive biases in workplace decision-making* - baseline: Ohms, B. (2025), "A Systematic Literature Review of Cognitive Biases in Workplace Decision-Making," *International Journal of Business Administration*, 16(3). doi:10.5430/ijba.v16n3p26
  2. *AI integration in supply chain management* - baseline: Samuels, A. (2025), "Examining the integration of artificial intelligence in supply chain management from Industry 4.0 to 6.0: a systematic literature review," *Frontiers in Artificial Intelligence*. doi:10.3389/frai.2024.1477044
  3. *AI in hospital management* - baseline: Bhagat, S.V. & Kanyal, D. (2024), "Navigating the Future: The Transformative Impact of Artificial Intelligence on Hospital Management - A Comprehensive Review," *Cureus*, 16(2). PMC10955674
- **Models (2):** Gemini 2.5 Flash and Qwen3.5-27B.
- **Conditions (2):** RAG-only (local corpus) and RAG + web search.
- **Raters (3):** three independent raters scored each (topic, model, condition) report alongside an anonymized version of the corresponding published baseline review. Reports were shuffled within each topic and labeled only with neutral identifiers, so raters did not know which report came from which source.
- **Rubric (5 dimensions, 1-5 Likert):** Correctness, Coverage, Coherence, Usefulness, Citation Quality. See `rubric.md` for operational definitions.

## `ai_reports/` naming

Files are named `topic<N>_<model>_<condition>.md` where:

- `<N>` in {1, 2, 3} - the three topics above
- `<model>` in {gemini, qwen3.5}
  - `gemini` = Gemini 2.5 Flash
  - `qwen3.5` = Qwen3.5-27B (run with thinking mode disabled)
- `<condition>` in {rag-only, rag-web}

This gives 3 topics x 2 models x 2 conditions = 12 files.

## Results summary

### Inter-rater reliability (ICC)

| Dimension        | ICC(2,k) | F     | p       |
|------------------|----------|-------|---------|
| Correctness      | 0.764    | 5.41  | <0.001  |
| Coverage         | 0.819    | 7.44  | <0.001  |
| Coherence        | 0.842    | 7.13  | <0.001  |
| Usefulness       | 0.916    | 11.86 | <0.001  |
| Citation Quality | 0.908    | 14.09 | <0.001  |
| Total (sum of 5) | 0.902    | 15.32 | <0.001  |

ICC(2,k) is the two-way random effects average-measures model, appropriate for generalizing to other potential raters. All dimensions show statistically significant agreement (p < 0.001). Using established thresholds, values indicate good reliability for Correctness (0.764) and excellent reliability for every other dimension.

### Mean ratings by model and condition

Averaged across 3 topics and 3 raters. Columns: Corr. = Correctness, Cov. = Coverage, Coh. = Coherence, Use. = Usefulness, Cit.Q. = Citation Quality; Total is the sum across the five dimensions (maximum 25).

| Source                         | Corr. | Cov. | Coh. | Use. | Cit.Q. | Total |
|--------------------------------|-------|------|------|------|--------|-------|
| Published reviews (anonymized) | 2.11  | 2.89 | 3.22 | 2.44 | 1.78   | 12.44 |
| Gemini 2.5 Flash (RAG only)    | 2.56  | 3.67 | 3.33 | 2.67 | 1.44   | 13.67 |
| Gemini 2.5 Flash (RAG + web)   | 2.56  | 4.11 | 4.22 | 3.11 | 1.56   | 15.56 |
| Qwen3.5-27B (RAG only)         | 2.67  | 4.56 | 4.11 | 3.78 | 2.44   | 17.56 |
| Qwen3.5-27B (RAG + web)        | 3.11  | 4.11 | 4.22 | 4.00 | 3.22   | 18.67 |

All MAESTRO-generated reports received higher total scores than the anonymized published baselines across every model and condition combination. The best configuration (Qwen3.5-27B with web search) scored 18.67 / 25 compared to 12.44 / 25 for the published baselines.

### Effect of web search

Averaged across 2 models and 3 topics.

| Dimension        | RAG Only | RAG + Web | Difference |
|------------------|----------|-----------|------------|
| Correctness      | 2.61     | 2.83      | +0.22      |
| Coverage         | 4.11     | 4.11      | +0.00      |
| Coherence        | 3.72     | 4.22      | +0.50      |
| Usefulness       | 3.22     | 3.56      | +0.33      |
| Citation Quality | 1.94     | 2.39      | +0.44      |
| **Total**        | **15.61**| **17.11** | **+1.50**  |

Enabling web search improved total scores by an average of 1.50 points, with the largest gains in Coherence (+0.50) and Citation Quality (+0.44); four of the five dimensions improved, with Coverage unchanged.

## Data availability

The MAESTRO-generated reports in `ai_reports/` are released under the repository's AGPL-3.0 license. The anonymized published baseline reviews used for comparison are not redistributed: their full text remains the copyright of the respective original authors. The three baselines can be obtained from the DOIs listed under "Topics" above.

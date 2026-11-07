# Claude Haiku 5.5 — full-cohort results

Run: 2026-10-23 23:58 → 2026-10-24 08:07 EDT, `anthropic/claude-haiku-5-5`,
concurrency 10, 8387/8387 variants, 0 errors (795 rate-limit backoffs absorbed).
Metrics computed on one row per variant (`haiku_metrics.json`).

## Accuracy

| Metric | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| Exact match (5-class) | 43.52% | 50.17% | 58.03% |
| Directional (3-class)  | 50.66% | 59.70% | 71.58% |
| Macro F1               | 0.339  | 0.428  | 0.545 |

All three on the identical 8387-variant cohort (Sonnet/Opus files were deduped
to one row per variant first; raw line counts were 9092 and 8549 because retried
rows are appended, not replaced).

## Haiku per-class

| Class | Prec | Recall | F1 | Support |
|---|---|---|---|---|
| Pathogenic             | 0.825 | 0.059 | 0.110 | 2003 |
| Likely Pathogenic      | 0.285 | 0.118 | 0.167 | 1546 |
| Uncertain Significance | 0.400 | 0.973 | 0.567 | 2779 |
| Likely Benign          | 0.476 | 0.099 | 0.164 | 1118 |
| Benign                 | 0.875 | 0.566 | 0.688 |  941 |
| **Macro** | **0.572** | **0.363** | **0.339** | |

## Haiku directional

| Direction | Prec | Recall | F1 | Support |
|---|---|---|---|---|
| pathogenic | 0.969 | 0.214 | 0.351 | 3549 |
| vus        | 0.400 | 0.973 | 0.567 | 2779 |
| benign     | 0.930 | 0.380 | 0.540 | 2059 |

## Note

Haiku collapses the cohort into VUS: recall 0.973 on Uncertain Significance
against 0.059 on Pathogenic. Where it does commit, it is accurate — pathogenic
precision 0.969, benign 0.930 — so the failure is abstention, not mislabelling.

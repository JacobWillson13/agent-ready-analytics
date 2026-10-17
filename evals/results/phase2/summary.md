# Benchmark results: phase2

64 questions, 1152 executions, models: Claude Haiku 5.5, Gemma 4 26B (local).

## Accuracy

| group | model | level | n_questions | n_runs | accuracy | CI |
|---|---|---|---|---|---|---|
| all | Claude Haiku 5.5 | raw | 64 | 192 | 65.6 | 56 to 75 |
| all | Claude Haiku 5.5 | docs | 64 | 192 | 99.5 | 98 to 100 |
| all | Claude Haiku 5.5 | full | 64 | 192 | 93.8 | 88 to 98 |
| all | Gemma 4 26B (local) | raw | 64 | 192 | 22.9 | 14 to 33 |
| all | Gemma 4 26B (local) | docs | 64 | 192 | 68.2 | 58 to 78 |
| all | Gemma 4 26B (local) | full | 64 | 192 | 83.3 | 75 to 92 |
| original | Claude Haiku 5.5 | raw | 31 | 93 | 72.0 | 59 to 84 |
| original | Claude Haiku 5.5 | docs | 31 | 93 | 100.0 | 100 to 100 |
| original | Claude Haiku 5.5 | full | 31 | 93 | 93.5 | 84 to 100 |
| original | Gemma 4 26B (local) | raw | 31 | 93 | 26.9 | 13 to 42 |
| original | Gemma 4 26B (local) | docs | 31 | 93 | 80.6 | 68 to 92 |
| original | Gemma 4 26B (local) | full | 31 | 93 | 88.2 | 77 to 97 |
| hard | Claude Haiku 5.5 | raw | 33 | 99 | 59.6 | 45 to 74 |
| hard | Claude Haiku 5.5 | docs | 33 | 99 | 99.0 | 97 to 100 |
| hard | Claude Haiku 5.5 | full | 33 | 99 | 93.9 | 86 to 100 |
| hard | Gemma 4 26B (local) | raw | 33 | 99 | 19.2 | 7 to 32 |
| hard | Gemma 4 26B (local) | docs | 33 | 99 | 56.6 | 42 to 70 |
| hard | Gemma 4 26B (local) | full | 33 | 99 | 78.8 | 66 to 91 |

## Paired contrasts (percentage points, question-clustered bootstrap)

| group | contrast | model | diff | CI | n |
|---|---|---|---|---|---|
| all | docs - raw | Claude Haiku 5.5 | +33.9 | +25.0 to +43.8 | 64 |
| all | full - raw | Claude Haiku 5.5 | +28.1 | +17.2 to +39.6 | 64 |
| all | full - docs | Claude Haiku 5.5 | -5.7 | -12.0 to -0.5 | 64 |
| all | docs - raw | Gemma 4 26B (local) | +45.3 | +32.8 to +57.3 | 64 |
| all | full - raw | Gemma 4 26B (local) | +60.4 | +48.4 to +71.4 | 64 |
| all | full - docs | Gemma 4 26B (local) | +15.1 | +4.7 to +25.5 | 64 |
| all | Gemma 4 26B (local) - Claude Haiku 5.5 | raw | -42.7 | -52.6 to -32.8 | 64 |
| all | Gemma 4 26B (local) - Claude Haiku 5.5 | docs | -31.2 | -41.2 to -22.4 | 64 |
| all | Gemma 4 26B (local) - Claude Haiku 5.5 | full | -10.4 | -18.2 to -2.6 | 64 |
| original | docs - raw | Claude Haiku 5.5 | +28.0 | +16.1 to +40.9 | 31 |
| original | full - raw | Claude Haiku 5.5 | +21.5 | +5.4 to +37.6 | 31 |
| original | full - docs | Claude Haiku 5.5 | -6.5 | -16.1 to +0.0 | 31 |
| original | docs - raw | Gemma 4 26B (local) | +53.8 | +33.3 to +71.0 | 31 |
| original | full - raw | Gemma 4 26B (local) | +61.3 | +45.1 to +77.4 | 31 |
| original | full - docs | Gemma 4 26B (local) | +7.5 | -5.4 to +20.4 | 31 |
| original | Gemma 4 26B (local) - Claude Haiku 5.5 | raw | -45.2 | -60.2 to -31.2 | 31 |
| original | Gemma 4 26B (local) - Claude Haiku 5.5 | docs | -19.4 | -32.3 to -7.5 | 31 |
| original | Gemma 4 26B (local) - Claude Haiku 5.5 | full | -5.4 | -17.2 to +5.4 | 31 |
| hard | docs - raw | Claude Haiku 5.5 | +39.4 | +26.3 to +53.5 | 33 |
| hard | full - raw | Claude Haiku 5.5 | +34.3 | +20.2 to +49.5 | 33 |
| hard | full - docs | Claude Haiku 5.5 | -5.1 | -14.1 to +1.0 | 33 |
| hard | docs - raw | Gemma 4 26B (local) | +37.4 | +23.2 to +52.5 | 33 |
| hard | full - raw | Gemma 4 26B (local) | +59.6 | +41.4 to +75.8 | 33 |
| hard | full - docs | Gemma 4 26B (local) | +22.2 | +7.1 to +38.4 | 33 |
| hard | Gemma 4 26B (local) - Claude Haiku 5.5 | raw | -40.4 | -53.5 to -27.2 | 33 |
| hard | Gemma 4 26B (local) - Claude Haiku 5.5 | docs | -42.4 | -56.6 to -29.3 | 33 |
| hard | Gemma 4 26B (local) - Claude Haiku 5.5 | full | -15.2 | -27.3 to -5.1 | 33 |

At full context, Gemma 4 26B (local) - Claude Haiku 5.5 = -10.4 points (95% CI -18.2 to -2.6). With a non-inferiority margin of 10 points, the local model does not meet the bar.

## Mixed-effects logistic model (all questions)

| Term | Estimate (log-odds) | SD | Approx. 95% interval |
|---|---|---|---|
| Intercept | +1.11 | 0.09 | +0.92 to +1.29 |
| model=b_ollama_gemma4_26b | -2.93 | 0.12 | -3.17 to -2.70 |
| level=docs | +4.61 | 0.18 | +4.26 to +4.96 |
| level=full | +2.70 | 0.18 | +2.34 to +3.06 |
| model=b_ollama_gemma4_26b x level=docs | -1.51 | 0.19 | -1.88 to -1.15 |
| model=b_ollama_gemma4_26b x level=full | +1.55 | 0.22 | +1.12 to +1.99 |

Question random-intercept SD (log-odds): 1.87. Reference cell: Claude Haiku 5.5 at raw context.

## Cost, latency, and tool use

| model | level | runs | failure_rate | tool_calls_median | input_tokens_median | output_tokens_median | latency_p50 | latency_p95 | cost_per_question | total_cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Claude Haiku 5.5 | raw | 192 | 0.0 | 11 | 47,793 | 4,110 | 34.2 | 66.8 | $0.0090 | $1.72 |
| Claude Haiku 5.5 | docs | 192 | 0.0 | 9 | 16,536 | 1,483 | 12.1 | 25.5 | $0.0030 | $0.58 |
| Claude Haiku 5.5 | full | 192 | 0.0 | 6 | 17,480 | 1,298 | 14.1 | 28.0 | $0.0028 | $0.53 |
| Gemma 4 26B (local) | raw | 192 | 23.4 | 7 | 15,170 | 1,018 | 17.9 | 42.5 | $0.0000 | $0.00 |
| Gemma 4 26B (local) | docs | 192 | 21.9 | 8 | 12,151 | 704 | 10.2 | 27.3 | $0.0000 | $0.00 |
| Gemma 4 26B (local) | full | 192 | 11.5 | 3 | 6,270 | 330 | 10.2 | 24.8 | $0.0000 | $0.00 |

## Execution status

| model | ok | recursion_limit |
|---|---|---|
| Claude Haiku 5.5 | 576 | 0 |
| Gemma 4 26B (local) | 467 | 109 |

## Accuracy by trap (%)

| trap | Claude Haiku 5.5 raw | Claude Haiku 5.5 docs | Claude Haiku 5.5 full | Gemma 4 26B (local) raw | Gemma 4 26B (local) docs | Gemma 4 26B (local) full |
|---|---|---|---|---|---|---|
| arr_summed_over_months | 67 | 100 | 80 | 0 | 87 | 100 |
| customer_identity | 51 | 100 | 100 | 8 | 69 | 79 |
| internal_usage | 78 | 100 | 100 | 44 | 72 | 86 |
| invoice_double_count | 53 | 100 | 100 | 0 | 67 | 100 |
| price_book_change | 100 | 100 | 100 | 100 | 83 | 100 |
| seats_are_a_balance | 44 | 100 | 78 | 0 | 33 | 78 |
| segment_duplicates | 100 | 100 | 100 | 33 | 56 | 56 |
| self_hosted_no_telemetry | 100 | 100 | 100 | 78 | 89 | 100 |
| sf_deployment_stale | 100 | 100 | 100 | 78 | 89 | 100 |
| stale_status | 88 | 100 | 88 | 0 | 71 | 58 |
| tcv_vs_arr | 62 | 97 | 90 | 8 | 59 | 85 |
| two_revenue_streams | 43 | 98 | 93 | 7 | 67 | 100 |
| upgrade_is_not_churn | 53 | 100 | 100 | 7 | 60 | 53 |

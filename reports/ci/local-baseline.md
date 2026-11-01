# dev10

Summary: {"selected": 10, "attempted": 10, "passed": 9, "failed": 1, "errors": 0, "judge_errors": 0, "not_executed": 0, "complete": true, "coverage": 1.0, "pass_rate": 0.9, "confirmed_passed_of_planned": "9/10"}

| Case | Outcome | Run | Failed checks |
|---|---|---|---|
| pool-exhaustion-01 | passed | ad9e59f8-5cbc-436c-a5e9-56f3eb85acec |  |
| w6-pool-exhaustion-02 | passed | ecda044e-9f2e-459c-8e28-00e47d769728 |  |
| w6-downstream-timeout-01 | passed | 8c2c34de-d366-40d7-b51f-b9863b257d7a |  |
| w6-config-regression-01 | passed | 5d9f21e6-5fae-4966-9f66-2722337f8b94 |  |
| w6-memory-pressure-01 | passed | 0203c183-5c1b-4640-b767-c6dc490bce68 |  |
| w6-traffic-spike-01 | passed | 301cb8c4-0c82-4a22-ba03-fc302a3071e8 |  |
| w6-healthy-01 | passed | 6704e201-52cc-4aea-9e75-08401f1d84be |  |
| w6-insufficient-01 | failed | ae83c087-87ee-418f-b282-c1d3942bf09c | cause_terms |
| w6-db-lock-wait-01 | passed | 98275af5-c956-4efd-a33f-ac01767744fb |  |
| w6-db-lock-wait-02 | passed | 6411920a-a8be-4f4e-8500-ab4c680fce38 |  |

## Frozen experiment

Prompt: `b607124299c8683f22704cd8a32a2dd92c06469887a1aa89d10676128091bdbb`; commit: `None`.
Evaluator: `bc0b366ec248ee3f2ebf38498959647aa55b5170fa2e60174e8560c9096139e3`; dataset: `913c65c6994772b7060f31ae1f1ef446eedec0c3838a532119b3f8b897a5f3c3`.
Budget: `{"limit_usd": "0.20", "known_spent_usd": "0.011233566", "model_calls": 35, "unknown_usage": false, "note": "Conservative application-side reserve; not a provider billing cap."}`.

| Family | Attempted | Passed | Quality failed | Execution errors |
|---|---:|---:|---:|---:|
| pool-exhaustion | 2 | 2 | 0 | 0 |
| downstream-timeout | 1 | 1 | 0 | 0 |
| config-regression | 1 | 1 | 0 | 0 |
| memory-pressure | 1 | 1 | 0 | 0 |
| traffic-spike | 1 | 1 | 0 | 0 |
| healthy | 1 | 1 | 0 | 0 |
| insufficient | 1 | 0 | 1 | 0 |
| db-lock-wait | 2 | 2 | 0 | 0 |

## Failure categories

Counts may overlap; these are observable rule failures, not causal claims.

- root_cause_rules_unmet: 1

Not executed: [].

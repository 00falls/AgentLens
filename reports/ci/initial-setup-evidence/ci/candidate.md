# dev10

Summary: {"selected": 10, "attempted": 9, "passed": 7, "failed": 1, "errors": 1, "judge_errors": 0, "not_executed": 1, "complete": false, "coverage": 0.9, "pass_rate": null, "confirmed_passed_of_planned": "7/10"}

| Case | Outcome | Run | Failed checks |
|---|---|---|---|
| pool-exhaustion-01 | passed | e37cbccc-b99e-4165-b7f7-85651412b10b |  |
| w6-pool-exhaustion-02 | passed | d732a9a3-4a31-4224-b0bb-8edb5fc03640 |  |
| w6-downstream-timeout-01 | failed | 89ca431e-a58a-4786-a445-5b7cc485ba1a | query_scope, trajectory_parameters |
| w6-config-regression-01 | passed | 60ab0cb2-7c0d-4536-827e-6a6533069df4 |  |
| w6-memory-pressure-01 | passed | 026e3194-f511-44c4-bb16-c0fb2771caf1 |  |
| w6-traffic-spike-01 | passed | d16db1a7-45db-4e49-b29c-e04df6ce795d |  |
| w6-healthy-01 | passed | 13d9cb69-6517-47c4-b30d-1f4d612fc245 |  |
| w6-insufficient-01 | execution_error | aef9786f-f78b-40e6-ae5c-9af288b981e2 | ValidationError: 1 validation error for Diagnosis   Invalid JSON: expected value at line 1 column 1 [type=json_invalid, input_value='该时间窗内 payment-...、指标与手册"]}', input_type=str]     For further information visit https://errors.pydantic.dev/2.14/v/json_invalid |
| w6-db-lock-wait-01 | passed | 1c7287eb-d6c6-4256-822e-bdc97cb52022 |  |

## Frozen experiment

Prompt: `b607124299c8683f22704cd8a32a2dd92c06469887a1aa89d10676128091bdbb`; commit: `1c94aae0cc01c94e6584ae94034b54c2f7406144`.
Evaluator: `bc0b366ec248ee3f2ebf38498959647aa55b5170fa2e60174e8560c9096139e3`; dataset: `913c65c6994772b7060f31ae1f1ef446eedec0c3838a532119b3f8b897a5f3c3`.
Budget: `{"limit_usd": "0.20", "known_spent_usd": "0.010199082", "model_calls": 33, "unknown_usage": false, "note": "Conservative application-side reserve; not a provider billing cap."}`.

| Family | Attempted | Passed | Quality failed | Execution errors |
|---|---:|---:|---:|---:|
| pool-exhaustion | 2 | 2 | 0 | 0 |
| downstream-timeout | 1 | 0 | 1 | 0 |
| config-regression | 1 | 1 | 0 | 0 |
| memory-pressure | 1 | 1 | 0 | 0 |
| traffic-spike | 1 | 1 | 0 | 0 |
| healthy | 1 | 1 | 0 | 0 |
| insufficient | 1 | 0 | 0 | 1 |
| db-lock-wait | 1 | 1 | 0 | 0 |

## Failure categories

Counts may overlap; these are observable rule failures, not causal claims.

- arguments_or_scope: 1
- execution_error: 1

Not executed: ['w6-db-lock-wait-02'].

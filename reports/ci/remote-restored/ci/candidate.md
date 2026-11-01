# dev10

Summary: {"selected": 10, "attempted": 10, "passed": 9, "failed": 1, "errors": 0, "judge_errors": 0, "not_executed": 0, "complete": true, "coverage": 1.0, "pass_rate": 0.9, "confirmed_passed_of_planned": "9/10"}

| Case | Outcome | Run | Failed checks |
|---|---|---|---|
| pool-exhaustion-01 | passed | e620d595-0174-4a08-acc8-b0c76272601d |  |
| w6-pool-exhaustion-02 | passed | 5a6423a0-7f51-4233-98b6-bc37c3ecbaef |  |
| w6-downstream-timeout-01 | passed | 59e42697-f92e-4e29-a7f4-3540a6945ff4 |  |
| w6-config-regression-01 | passed | 9a17616e-196f-4a93-af3e-ae6a05adce8a |  |
| w6-memory-pressure-01 | passed | 3bf35faa-d55f-4916-8039-11a9dd5a5e61 |  |
| w6-traffic-spike-01 | passed | 8598dd39-28a9-4a32-9cd5-d1b0d8840136 |  |
| w6-healthy-01 | passed | f7ad8e76-0778-4068-a5d7-f51f53a52ff3 |  |
| w6-insufficient-01 | failed | 4ea1f04e-d7ac-4741-8364-c4e1a4d4011b | cause_terms |
| w6-db-lock-wait-01 | passed | e5bba761-dd16-4ac9-9f92-8bee54d617fb |  |
| w6-db-lock-wait-02 | passed | 0ec62e21-8a1a-4235-b401-a17ad91e3cbc |  |

## Frozen experiment

Prompt: `6a2ed524c13ae7580e8ea2f263a849042938b6dc8243414948269645ed2f8502`; commit: `f651719f205ff978acd26671d359a14a0f943635`.
Evaluator: `bc0b366ec248ee3f2ebf38498959647aa55b5170fa2e60174e8560c9096139e3`; dataset: `913c65c6994772b7060f31ae1f1ef446eedec0c3838a532119b3f8b897a5f3c3`.
Budget: `{"limit_usd": "0.20", "known_spent_usd": "0.009911268", "model_calls": 35, "unknown_usage": false, "note": "Conservative application-side reserve; not a provider billing cap."}`.

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

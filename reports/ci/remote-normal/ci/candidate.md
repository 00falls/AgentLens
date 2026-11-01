# dev10

Summary: {"selected": 10, "attempted": 10, "passed": 8, "failed": 2, "errors": 0, "judge_errors": 0, "not_executed": 0, "complete": true, "coverage": 1.0, "pass_rate": 0.8, "confirmed_passed_of_planned": "8/10"}

| Case | Outcome | Run | Failed checks |
|---|---|---|---|
| pool-exhaustion-01 | passed | c8700eca-6603-4bc4-9dd6-2e407375d8aa |  |
| w6-pool-exhaustion-02 | passed | f32b8e68-4f20-4ed9-b2ba-9730d9f2ef41 |  |
| w6-downstream-timeout-01 | passed | f57081ac-27a2-439d-aa1e-62c25679a82c |  |
| w6-config-regression-01 | passed | 885edb50-6304-4823-8dd3-a6054832d40a |  |
| w6-memory-pressure-01 | passed | bf66b52b-bd07-4362-84f6-5b2efdeea09a |  |
| w6-traffic-spike-01 | passed | c2095f12-2ab5-4ff8-b891-be844af1046c |  |
| w6-healthy-01 | failed | d1f052c5-3cbe-4617-a030-70b66cd59ea3 | cause_terms |
| w6-insufficient-01 | failed | 88f9a283-46bf-4a69-83e6-f0a20bd5aea4 | cause_terms |
| w6-db-lock-wait-01 | passed | 422b3485-ec2f-47fc-bcbe-8654faaf5641 |  |
| w6-db-lock-wait-02 | passed | dd79b0d5-f1da-4215-b38c-e1beb1d83305 |  |

## Frozen experiment

Prompt: `6a2ed524c13ae7580e8ea2f263a849042938b6dc8243414948269645ed2f8502`; commit: `d3d94c04f51a600a0d75b9fd8c75595ff29bf95d`.
Evaluator: `bc0b366ec248ee3f2ebf38498959647aa55b5170fa2e60174e8560c9096139e3`; dataset: `913c65c6994772b7060f31ae1f1ef446eedec0c3838a532119b3f8b897a5f3c3`.
Budget: `{"limit_usd": "0.20", "known_spent_usd": "0.010976052", "model_calls": 34, "unknown_usage": false, "note": "Conservative application-side reserve; not a provider billing cap."}`.

| Family | Attempted | Passed | Quality failed | Execution errors |
|---|---:|---:|---:|---:|
| pool-exhaustion | 2 | 2 | 0 | 0 |
| downstream-timeout | 1 | 1 | 0 | 0 |
| config-regression | 1 | 1 | 0 | 0 |
| memory-pressure | 1 | 1 | 0 | 0 |
| traffic-spike | 1 | 1 | 0 | 0 |
| healthy | 1 | 0 | 1 | 0 |
| insufficient | 1 | 0 | 1 | 0 |
| db-lock-wait | 2 | 2 | 0 | 0 |

## Failure categories

Counts may overlap; these are observable rule failures, not causal claims.

- root_cause_rules_unmet: 2

Not executed: [].

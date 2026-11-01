# dev10

Summary: {"selected": 10, "attempted": 10, "passed": 0, "failed": 10, "errors": 0, "judge_errors": 0, "not_executed": 0, "complete": true, "coverage": 1.0, "pass_rate": 0.0, "confirmed_passed_of_planned": "0/10"}

| Case | Outcome | Run | Failed checks |
|---|---|---|---|
| pool-exhaustion-01 | failed | 0063c380-77f6-401b-9090-6b89a9a0f0ad | status, required_tools, cause_terms, required_evidence, runbook_retrieved, runbook_cited, trajectory_required_tools, trajectory_order |
| w6-pool-exhaustion-02 | failed | fdee6ece-d98a-46a6-82b9-f7daa3b7394b | status, required_tools, cause_terms, required_evidence, runbook_retrieved, runbook_cited, trajectory_required_tools, trajectory_order |
| w6-downstream-timeout-01 | failed | ba4181ff-5f61-4381-92d7-de9fead01ca9 | status, required_tools, cause_terms, required_evidence, runbook_retrieved, runbook_cited, trajectory_required_tools, trajectory_order |
| w6-config-regression-01 | failed | f12cfbef-5ca1-4c2b-8dfc-fa1705c07992 | status, required_tools, cause_terms, required_evidence, runbook_retrieved, runbook_cited, trajectory_required_tools, trajectory_order |
| w6-memory-pressure-01 | failed | 22d09476-a354-4bc1-bfe0-5a110bb743bb | status, required_tools, cause_terms, required_evidence, runbook_retrieved, runbook_cited, trajectory_required_tools, trajectory_order |
| w6-traffic-spike-01 | failed | 865adbbc-62a8-4280-bfac-587eb73a137b | status, required_tools, cause_terms, required_evidence, runbook_retrieved, runbook_cited, trajectory_required_tools, trajectory_order |
| w6-healthy-01 | failed | bec01c0a-651a-4ed4-9427-e6672e5ebe06 | required_tools, cause_terms, trajectory_required_tools |
| w6-insufficient-01 | failed | 12b10488-1abb-47cb-bb71-2959a48c7345 | required_tools, trajectory_required_tools |
| w6-db-lock-wait-01 | failed | 1d3d2a5b-1ba8-4757-9e5a-5fce4d7c094f | status, required_tools, cause_terms, required_evidence, runbook_retrieved, runbook_cited, trajectory_required_tools, trajectory_order |
| w6-db-lock-wait-02 | failed | 930528d6-3017-484e-ad43-35f730ed4e63 | status, required_tools, cause_terms, required_evidence, runbook_retrieved, runbook_cited, trajectory_required_tools, trajectory_order |

## Frozen experiment

Prompt: `22cf5f8ee462cee365944395055479e4f121c166d2d1dea78a790d40eb6789f5`; commit: `4f6f082e147a585a7dff20545bea634263badc4b`.
Evaluator: `bc0b366ec248ee3f2ebf38498959647aa55b5170fa2e60174e8560c9096139e3`; dataset: `913c65c6994772b7060f31ae1f1ef446eedec0c3838a532119b3f8b897a5f3c3`.
Budget: `{"limit_usd": "0.20", "known_spent_usd": "0.000925392", "model_calls": 10, "unknown_usage": false, "note": "Conservative application-side reserve; not a provider billing cap."}`.

| Family | Attempted | Passed | Quality failed | Execution errors |
|---|---:|---:|---:|---:|
| pool-exhaustion | 2 | 0 | 2 | 0 |
| downstream-timeout | 1 | 0 | 1 | 0 |
| config-regression | 1 | 0 | 1 | 0 |
| memory-pressure | 1 | 0 | 1 | 0 |
| traffic-spike | 1 | 0 | 1 | 0 |
| healthy | 1 | 0 | 1 | 0 |
| insufficient | 1 | 0 | 1 | 0 |
| db-lock-wait | 2 | 0 | 2 | 0 |

## Failure categories

Counts may overlap; these are observable rule failures, not causal claims.

- tool_selection_or_order: 10
- citation_missing_or_invalid: 8
- root_cause_rules_unmet: 9
- runbook_not_queried: 8

Not executed: [].

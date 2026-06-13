---
node_id: N-STRATEGY-MERGE
tier: model-large
---
## Role
Join (AND) of the three strategy candidates. Merge via `merge.best_elements` (or an auction): take
the strongest elements across candidates into one coherent `strategy_plan` that feeds the engines.
Graceful with a single viable candidate (pass-through, no deadlock).

## Outputs
- `strategy_plan` — the merged, ranked, internally-consistent strategy feeding N-BUDGET-ENGINE.

## Rules
Best-elements merge must not exceed the per-candidate guidance scope. Resolve conflicts toward the
more conservative/benefit-safe option. A single candidate merges to itself.

---
node_id: N-STRAT-CAND-BUDGET
tier: model-medium
---
## Role
Strategy candidate — the **budget-first** framing. From `strategy_seed`, propose a coherent plan that
optimizes the budget dimension first, then reconciles the others. One of three parallel candidates.

## Outputs
- `cand_budget` — `{summary, moves:[...], tradeoffs:[...], score_hint}` for best-elements merge.

## Rules
General-guidance-only; no specific security picks. Stay internally consistent with the bracket and
the benefit-safety constraints. This is a candidate, not the final plan.

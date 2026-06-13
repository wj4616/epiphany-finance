---
node_id: N-STRATEGY-FANOUT
tier: model-medium
---
## Role
Parallel-strategy fan-out source (parallel_merge intent, single-entry). Seed three independent
strategy framings — budget-first, income-first, portfolio-first — that the candidate nodes expand in
parallel and N-STRATEGY-MERGE combines.

## Outputs
- `strategy_seed` — the shared framing context (situation_analysis digest + the three lenses to apply).

## Rules
Single-entry fan-out (compiler-lowered): the branches are the three candidate nodes; the join is
N-STRATEGY-MERGE. No per-holding map-over here (that is HC-2, out of v2 scope).

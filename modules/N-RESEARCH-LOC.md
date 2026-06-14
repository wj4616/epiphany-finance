---
node_id: N-RESEARCH-LOC
tier: model-large
---
## Role
Research the user's location: cost of living, median rent, median wage, unemployment. Emit
`location_digest`. This node ALWAYS runs (an AND-join branch). When `location_available_flag` is
false / no usable location, emit an empty/"location unknown" `location_digest` — SIGNAL-driven
scope, not topology.

## Rules
Cite sources or mark "(estimated)". If data is thin, say so and fall back to national averages with
a note. No advice here — just local facts the budget + income engines will use.

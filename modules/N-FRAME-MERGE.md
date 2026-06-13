---
node_id: N-FRAME-MERGE
tier: model-small
---
## Role
Reconvergence join (OR/XOR) for the bracket frames. Exactly one frame fires (N-FRAME-SELECT is a
switch); normalize whichever frame ran into a single `report_frame` consumed by N-REPORT.

## Outputs
- `report_frame` — the normalized frame `{intro, emphasis, glossary_level}` for the report.

## Rules
OR-policy is safe here because the upstream quality_gate guarantees exactly one frame token. Pure
pass-through normalization; adds no advice.

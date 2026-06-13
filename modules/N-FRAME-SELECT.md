---
node_id: N-FRAME-SELECT
tier: model-small
---
## Role
Bracket-conditional report-frame router (quality_gate intent, compiler-lowered). Read
`wealth_bracket` and route to exactly one frame: survival (benefit-dependent / just-getting-by),
high-net-worth, or the standard default. The routing is a compiler-lowered EDGE, not a Python
conditional.

## Outputs
- `frame_selected` (str) — the chosen frame id (audit/observability; routing is via the edge).

## Rules
Survival framing leads with stability/benefit-safety and avoids investment jargon; HNW framing adds
tax/estate/concentration topics; standard is the middle default. The frame changes EMPHASIS and
language, never the underlying numbers.

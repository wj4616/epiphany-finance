---
node_id: N-FRAME-SELECT
tier: model-small
---
## Role
Report-frame router (quality_gate intent, compiler-lowered). Read `wealth_bracket` and
`benefit_dependent` and route to exactly one frame: survival (benefit-dependent OR a just-getting-by
bracket — destitute/homeless/working-poor), high-net-worth (wealthy/ultra-HNW), or the standard
default (everyone else). The routing is a compiler-lowered EDGE, not a Python conditional. NOTE: the
gate compares actual `wealth_bracket` VALUES — never the frame ids 'survival'/'hnw' (which are not
bracket values; doing so makes every user fall through to standard and silently kills the survival
frame).

## Outputs
- `frame_selected` (str) — the chosen frame id (audit/observability; routing is via the edge).

## Rules
Survival framing leads with stability/benefit-safety and avoids investment jargon; HNW framing adds
tax/estate/concentration topics; standard is the middle default. The frame changes EMPHASIS and
language, never the underlying numbers.

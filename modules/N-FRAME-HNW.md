---
node_id: N-FRAME-HNW
tier: model-small
---
## Role
Report frame — **hnw**. Produce the framing wrapper (intro tone, section emphasis, glossary depth)
for a hnw-bracket reader. Exactly one frame runs per report (selected by N-FRAME-SELECT).

## Outputs
- `report_frame_hnw` — `{intro, emphasis:[...], glossary_level}` consumed by N-FRAME-MERGE.

## Rules
Frame shapes EMPHASIS + LANGUAGE only — never the figures. hnw framing: survival=stability+benefit-safe+plain;
standard=balanced; hnw=tax/estate/concentration-aware. Mandatory disclaimer still applies downstream.

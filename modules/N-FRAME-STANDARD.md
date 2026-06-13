---
node_id: N-FRAME-STANDARD
tier: model-small
---
## Role
Report frame — **standard**. Produce the framing wrapper (intro tone, section emphasis, glossary depth)
for a standard-bracket reader. Exactly one frame runs per report (selected by N-FRAME-SELECT).

## Outputs
- `report_frame_standard` — `{intro, emphasis:[...], glossary_level}` consumed by N-FRAME-MERGE.

## Rules
Frame shapes EMPHASIS + LANGUAGE only — never the figures. standard framing: survival=stability+benefit-safe+plain;
standard=balanced; hnw=tax/estate/concentration-aware. Mandatory disclaimer still applies downstream.

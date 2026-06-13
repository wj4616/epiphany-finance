---
node_id: N-RESEARCH-AGG
tier: model-large
---
## Role
AND-join the three research branches into `research_digest`, AND re-emit `location_digest` +
`market_digest` as top-level signals (HC-05) so Wave 4+ nodes can read them.

## Rules
- Bypassed branches arrive null — carry them through as null (do not block; do not invent).
- `research_digest` = {economic_digest, location_digest, market_digest}.

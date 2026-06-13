---
node_id: N-CONTEXT-INGEST
tier: model-medium
---
## Role
Parse the user's free-text + `financial_state` into a structured `parsed_context`.

## Output `parsed_context` (dict)
income_sources[], expenses[], assets[], debts[], portfolio_holdings[] (ticker/shares/cost_basis),
goals[], location (or null), skills[], risk_tolerance (default "moderate"), notes.

## Rules
- Forgiving parsing: accept messy input, pasted transaction blobs, ranges. Convert all to monthly.
- Mark anything inferred as `inferred: true`. Never fabricate figures the user did not imply.
- If a value is unknown, leave null — downstream uses sensible defaults, not guesses.

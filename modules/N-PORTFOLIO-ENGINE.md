---
node_id: N-PORTFOLIO-ENGINE
tier: model-large
---
## Role
Value the user's holdings with LIVE prices and suggest BROAD rebalancing. Emit `portfolio_plan`.
Only fires when `has_investment_flag` is true.

## Inputs
`quote_data` (from N-QUOTE-FETCHER — exact fetch_ts + per-ticker price/source_ts/staleness), holdings.

## Compute
- current_value per holding = shares × live_price; gains_losses = current_value − cost_basis.
- Refine compound projections using current_value as starting principal (not cost_basis).
- Rebalancing = move toward the bracket's BROAD targets (index/bonds/HYSA/REIT classes).

## Rules (Q5 — CRITICAL SAFETY)
- DO NOT compare specific securities, rank tickers, or recommend buying/selling specific stocks.
- Quotes are for VALUATION + BROAD rebalancing ONLY; note prices may be delayed.
- Every price/value carries its exact timestamp (Q2) and a staleness note.
- `quote_freshness_statement` summarizes the data's exact age.
- If quote_data.offline_flag: proceed with cached values + an explicit caveat.

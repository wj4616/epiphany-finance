---
name: epiphany-finance
description: >-
  Personal financial advisor for ANY wealth level (just getting by → ultra-high-net-worth). Use
  when the user asks for help with money, budgeting, saving, debt, income, a financial plan, or
  their investment portfolio — e.g. "help me with my budget", "can you look at my finances",
  "how should I save / invest", "am I on track", "make me a financial report". Runs a guided
  plain-language intake, builds a bidirectional budget + income plan, values any holdings with
  live (timestamped) Yahoo Finance prices, adversarially fact-checks every figure with an ENSEMBLE
  jury, surfaces benefit-cliff safety for SSDI/SSI/Medicaid/SNAP dependents, pauses once for your
  plain-text plan approval, and produces a friendly Markdown/PDF report with charts and a mandatory
  disclaimer. General guidance only — it does NOT pick stocks or compare specific securities.
---

# epiphany-finance (v2.0.0)

A full-power tier-3 goatcs-harness graph (36 nodes, GoT-full) + a Python wrapper. The wrapper handles
the human side (intake, SQLite state, live quotes, charts, PDF); the graph does the reasoning.

**v2 over v1.2.0 (all additive — every v1 guarantee preserved):**
- **Compiler-lowered conditional routing** — refuse (early_exit), bracket→report-frame (quality_gate),
  and multi-strategy fan-out (parallel_merge) are declared in `intent.json` and wired by the topology
  compiler, not hand-coded. (`graph.v2-base.json` + `intent.json` lower deterministically to `graph.json`.)
- **Ensemble adversarial verification** — every monetary figure is challenged by an N-of-M jury
  (default 3 jurors / 2-of-3 quorum); a dissenting figure lands in an UNCERTAIN appendix, never a
  silent pass. Downshifts to a single juror on the routine $0 inline path.
- **Multi-strategy reasoning fan-out** — budget/income/portfolio framings are generated in parallel and
  best-elements-merged into one strategy plan.
- **Benefit-safety** — for benefit-dependent users, flags cliffs, surfaces ABLE/earnings-limit options,
  and never recommends a silent benefit forfeit (cite-and-defer on jurisdiction-specific thresholds).
- **Macro grounding** — read-only, injection-hardened rates/inflation context with provenance.
- **One plan-approval pause** — a single plain-text HITL gate before the report finalizes (data intake
  stays wrapper-level). Approve → emit; rework → regenerate (bounded).
- **Live progress narration** — structured node-by-node progress is surfaced to the conversation.

Runs $0 inline by default (Opus). See `BUILD-REPORT-v2.md` for the full build record + disclosed
substrate-driven deviations.

## For a non-technical user (the common case)
Just say what you need ("help me with my money"). Then:
1. Run the guided setup: `epiphany-finance --mode intake` (plain questions, one at a time).
2. Get a report: `epiphany-finance --both`  (Markdown **and** PDF).
Next time, just run `epiphany-finance` — your info is saved locally (unencrypted) under
`~/.epiphany-finance/users/<you>/`; nothing is sent to your bank or stored online. Your data
**persists across sessions by default** — it stays even if you clear the chat.

**Starting over:** `epiphany-finance --reset` permanently wipes *your* saved data (asks you to
confirm first); `epiphany-finance --reset-all` wipes everyone's. Add `--yes` to skip the prompt.
This is the only thing that erases your data.

## How an agent (Claude Code) drives it — `inline` provider (default here)
The `inline` provider means **you, the agent, are the reasoner**. Flow:
1. `epiphany-finance --mode intake` (or call `wrapper.intake.run_intake`) → fills the SQLite state.
2. Prepare + drive the graph:
   ```
   epiphany-finance --provider inline --both          # writes <out>/seed.json + prints the drive cmd
   goatcs-harness run graph.json --seed <out>/seed.json --provider inline \
       --scratch-dir <out>/session
   ```
   The harness auto-runs the tool/routing nodes and PAUSES (exit 11) at each reasoning node with
   `{node, prompt, contract}`. Read the node's `modules/N-*.md` contract, produce the output, and
   `goatcs-harness submit --inline …`, then `run --resume`. Repeat to a PASS report.
3. Finalize (renders charts + PDF + persists): `epiphany-finance --finalize <out>/session --both`.

## Headless (no agent in the loop)
`epiphany-finance --provider codex --both` (or `claude-cli`) drives the whole graph via a model
subprocess and renders in one call. `--provider auto` picks inline when an agent drives, else codex.

## Modes & flags
`--mode {intake,analyze,budget,income,portfolio,report}` · `--markdown` / `--pdf` / `--both` ·
`--location "City, ST"` · `--update "<text>"` · `--db <path>` ·
`--provider {auto,inline,codex,claude-cli}` · `--reset` / `--reset-all` (+ `--yes`) wipe saved data.

## What it guarantees
- **Live, traceable quotes:** refreshed if >5 min old; every price shows the exact ISO8601 fetch +
  market timestamp. yfinance down → cached prices with a loud OFFLINE warning; >24h → STALE.
- **Bidirectional** budget (income→allocation AND expenses→income-target) and income (afford-now AND
  target+paths), exact compound projections (nominal + real).
- **Safety:** general guidance only — never specific stock picks or stock-vs-stock comparisons off
  possibly-delayed data. Quotes are used for valuation + broad rebalancing only.
- **Plain language:** every report has a "What this means for you" summary + a Glossary, a mandatory
  verbatim disclaimer top and bottom, and a Data Freshness section.

## Install
`bash install.sh` — checks Python, installs deps (yfinance, plotly, kaleido, weasyprint), deploys.
Full guide (runtime + extras + troubleshooting): **`INSTALL.md`**. Codex/gpt-5.5 variant (same graph,
provider swap — not a fork): **`SKILL-CODEX.md`** + `bash install-codex.sh`.

## Layout
`graph.json` (topology) · `modules/N-*.md` (node contracts) · `wrapper/` (state, quote, charts, pdf,
intake, finance, checks, disclaimer, workspace, run) · `fixtures/` (3 personas) · `tests/` (V-FIN-01..27
+ v2 battery + persistence/reset) · `wiring-contract.yaml` · `appendix.md` (domain canon) · `brief.md`
(v1 build brief — deployed graph is v2/36-node; see `BUILD-REPORT-v2.md`) · `INSTALL.md` · `SKILL-CODEX.md`.

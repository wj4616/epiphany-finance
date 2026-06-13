# epiphany-finance

A personal financial advisor skill for **any** wealth level (just getting by → ultra-high-net-worth),
built natively on the [goatcs-harness](https://github.com/wj4616/goatcs-harness) tier-3 graph runtime.
A 36-node graph does the reasoning; a Python wrapper handles the human side (intake, local state, live
quotes, charts, PDF).

> **General guidance only.** This skill does **not** pick stocks or compare specific securities, and
> every report carries a mandatory disclaimer. It is not a substitute for a licensed financial advisor.

## What it does

- Guided, plain-language intake — no jargon, one question at a time.
- **Bidirectional** budget (income→allocation *and* expenses→income-target) and income planning
  (afford-now *and* goal + concrete paths), with exact compound projections (nominal + real).
- Values any holdings with live, **timestamped** Yahoo Finance prices (OFFLINE/STALE-aware).
- Adversarially fact-checks every figure with an **ensemble jury**, routing unverifiable numbers to an
  UNCERTAIN appendix rather than asserting them.
- Surfaces **benefit-cliff safety** for SSDI / SSI / Medicaid / SNAP dependents.
- Pauses **once** for your plain-text plan approval, then produces a friendly Markdown/PDF report with
  charts and a verbatim disclaimer.

## Install

```bash
bash install.sh          # installs deps + deploys to ~/.claude/skills/
```

Full guide (runtime, optional extras, troubleshooting): **[INSTALL.md](INSTALL.md)**.
Requires the [goatcs-harness](https://github.com/wj4616/goatcs-harness) runtime (Python ≥ 3.11).

## Use

As a Claude Code skill, just ask — *"help me with my budget"*, *"am I on track"*. Or via CLI:

```bash
python3 -m wrapper.run --mode intake     # guided setup (first time)
python3 -m wrapper.run --both            # Markdown + PDF report
```

Your data **persists across sessions** under `~/.epiphany-finance/users/<you>/` (local, unencrypted,
nothing sent online). To start over: `--reset` (you) or `--reset-all` (everyone); add `--yes` to skip
the confirmation prompt.

**Codex / gpt-5.5 variant** — the same skill, provider-swapped (no rebuild): `bash install-codex.sh`,
then `python3 -m wrapper.run --both --provider codex`. See **[SKILL-CODEX.md](SKILL-CODEX.md)**.

## Layout

`graph.json` (topology) · `modules/N-*.md` (per-node reasoning contracts) · `wrapper/` (state, quote,
charts, pdf, intake, finance, checks, disclaimer, workspace, run) · `fixtures/` (3 personas) ·
`tests/` · `appendix.md` (domain canon) · `SKILL.md` / `SKILL-CODEX.md` (skill descriptors).

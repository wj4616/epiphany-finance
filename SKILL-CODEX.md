---
name: epiphany-finance-codex
description: >-
  Codex/gpt-5.5 entry point to the EXISTING epiphany-finance skill — same graph, same
  modules, same wrapper. Nothing is rebuilt: the goatcs-harness graph is provider-agnostic,
  so Codex simply reasons at each node instead of Claude. Use when you (Codex) are asked for
  help with money, budgeting, saving, debt, income, a financial plan, or a portfolio. Drives
  the 36-node graph headless via `codex exec`, holds every node to the machine fidelity gate,
  and renders the same friendly Markdown/PDF report. General guidance only — does NOT pick
  stocks or compare specific securities.
metadata:
  type: provider-variant
  parent_skill: epiphany-finance
  provider: codex
  model: gpt-5.5
  runtime: goatcs-harness
---

# epiphany-finance — Codex variant

This is **not a second skill**. It is the Codex/gpt-5.5 way to run the *same* deployed
`epiphany-finance` skill. The graph (`graph.json`, 36 nodes), the per-node reasoning
contracts (`modules/*.md`), and the Python wrapper (`wrapper/`) are **byte-identical** to
the Claude version. Only the reasoner changes — that is the whole point of building on a
graph runtime: **the machine routes/validates/replays; the model is pluggable.**

> Do not edit `graph.json`, `modules/`, `wrapper/`, or `SKILL.md` to "make a Codex version."
> There is nothing to change. Run the existing skill with `--provider codex`.

## Proven status

A bounded headless smoke (2026-06-13) drove the live graph with `--provider codex`:
codex/gpt-5.5 filled the first six reasoning nodes (PREFLIGHT → CONTEXT-INGEST → CLASSIFY →
research fan-out), and the **machine fidelity gate enforced the contract** — it *rejected*
one non-compliant submission (N-RESEARCH-ECO, reject_count=1), forced a retry, and codex
recovered to `accept`. Routing, checkpointing, and replay behaved identically to the Claude
path. The machine guarantees hold under Codex; node *reasoning quality* is gpt-5.5's.

## Prerequisites

- `codex` CLI on PATH (`codex --version`; preflight: `gpt-5.5` via `codex exec`).
- `goatcs-harness` importable (`pip install -e ~/projects/goatcs-harness`) **with the
  provider extra** — the codex provider imports `langchain-core` at load:
  `pip install -e '~/projects/goatcs-harness[providers]'`.
- The skill's own deps (quotes/charts/PDF) — see `INSTALL.md`.

## How to run

### A. Simplest — the wrapper drives it end-to-end (recommended)

```bash
cd ~/.claude/skills/epiphany-finance
python3 -m wrapper.run --both --provider codex          # or: EPIPHANY_PROVIDER=codex python3 -m wrapper.run --both
```

`--mode intake` first if this is a new user. The wrapper does the human side (intake,
SQLite state, live quotes, charts, PDF); the graph reasons; codex fills each node headless.
The single plan-approval HITL pause still applies. Saved data persists across runs under
`~/.epiphany-finance/users/<you>/`; wipe it with `--reset` / `--reset-all` (add `--yes` to skip
the confirm prompt in a headless run).

### B. Drive the graph directly via the harness (debugging / scripted)

```bash
cd ~/.claude/skills/epiphany-finance
PYTHONPATH=~/projects/goatcs-harness:. goatcs-harness run graph.json \
  --provider codex \
  --seed fixtures/seed_verify.json \
  --session ~/epiphany-harness-sessions/finance-codex/ \
  --scratch-dir /tmp/finance-codex-scratch
# then render from the completed session:
python3 -m wrapper.run --finalize ~/epiphany-harness-sessions/finance-codex/
```

`verify` first if you want the static gate: `goatcs-harness verify --strict-wiring graph.json`
(exit 0 = clean). Use `--max-steps N` to bound a smoke run; `--resume <session>` to continue.

## Caveats specific to the Codex path

1. **Reasoning is gpt-5.5, not Opus.** The *machine* guarantees (routing, contracts, gates,
   replay) are identical and proven. The *behavioral* V-battery (UNCERTAIN routing, the
   adversarial jury, plain-language output, benefit-cliff catches) was validated under Opus —
   do a full `--both` drive once and eyeball the report before trusting it for a real user.
2. **Ensemble jury degrades on a single-provider box.** `N-ADVERSARIAL` is a `jury_size=3`
   quorum. Headless with only codex available, the jury fills from available providers and
   collapses toward the J=1 path (safe — it routes a flagged figure to UNCERTAIN — but it is
   not a true cross-model jury). For a real 3-model jury, expose a second provider
   (`EPIPHANY_JURY`/cloud SDKs).
3. **Cost/latency.** A full run is up to ~36 `codex exec` calls — minutes and real Codex
   usage, unlike the instant/$0 inline-under-agent path.
4. **The fidelity gate may reject + retry** a node (as it did in the smoke). That is correct
   behavior, not an error — the contract is enforced regardless of model.

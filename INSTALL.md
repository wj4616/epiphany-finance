# Installing epiphany-finance

Personal financial advisor skill — a **goatcs-harness graph** (`graph.json`, v2.0.0,
36 nodes) plus a Python **wrapper** that handles intake, SQLite state, live quotes, and
chart/PDF rendering around the graph.

epiphany-finance has **two layers** to install:
1. the **runtime** — [goatcs-harness](../../../projects/goatcs-harness/INSTALL.md), which executes the graph;
2. the **skill's own deps** — quotes, charts, PDF.

---

## 1. Quick install (recommended)

From wherever this skill's source lives, run the bundled installer — it installs the
skill deps and deploys into `~/.claude/skills/`:

```bash
./install.sh
```

It then prints the run commands. The installer does **not** install the runtime —
do that once (step 2).

---

## 2. Install the runtime (goatcs-harness)

The graph cannot run without it.

```bash
cd ~/projects/goatcs-harness && pip install -e .
```

(See the harness [INSTALL.md](../../../projects/goatcs-harness/INSTALL.md) for details.)
If you prefer not to install it, make it importable per-invocation instead:

```bash
PYTHONPATH=~/projects/goatcs-harness  ...
```

> **Python ≥ 3.11.** The skill's own `pyproject.toml` says `>=3.8`, but the runtime
> requires **3.11+**, so 3.11+ is the effective floor.

---

## 3. Install the skill dependencies (manual alternative to `install.sh`)

```bash
python3 -m pip install yfinance "plotly>=6,<7" "kaleido==0.2.1" "weasyprint>=68" PyYAML
```

| Package | Pin | Purpose |
|---|---|---|
| `yfinance` | — | live, timestamped stock/ETF quotes (Yahoo Finance) |
| `plotly` | `>=6,<7` | chart figures (allocation, projections) |
| `kaleido` | `==0.2.1` | plotly → PNG/SVG export |
| `weasyprint` | `>=68` | Markdown/HTML → PDF report |
| `PyYAML` | — | module frontmatter |

**Linux system libs for WeasyPrint** (PDF rendering only):

```bash
sudo apt install libpango-1.0-0 libpangocairo-1.0-0
```

> **Kaleido version note.** This skill pins `kaleido==0.2.1` (what its renderer is
> built and tested against). The harness `[charts]` extra pins `kaleido>=1.0.0` for a
> different reason (suite teardown). If you install **both** in one environment the
> later install wins — for running this skill, keep `0.2.1`. Charts/PDF are optional:
> if quotes are offline or rendering deps are missing, the skill degrades to a
> chart-less report rather than failing.

---

## 4. Verify

```bash
cd ~/.claude/skills/epiphany-finance
PYTHONPATH=.:~/projects/goatcs-harness python -m pytest -q
```

**Expected:** `74 passed`. (That includes the V-FIN-01..27 carried battery + the v2
checks, and the two convergence-audit behavioral tests.)

Graph-level smoke:

```bash
PYTHONPATH=~/projects/goatcs-harness goatcs-harness verify --strict-wiring graph.json   # exit 0
```

---

## 5. Running it

**As a Claude Code skill (normal use).** Once deployed to `~/.claude/skills/epiphany-finance`,
just ask in plain language — *"help me with my budget"*, *"look at my finances"*,
*"am I on track"*. Claude drives the graph **inline** (no API key); it runs the guided
intake, pauses **once** for your plain-text plan approval, and produces the report.

**As a CLI** (headless / scripted):

```bash
cd ~/.claude/skills/epiphany-finance
python3 -m wrapper.run --mode intake      # guided plain-language intake
python3 -m wrapper.run --both             # build budget+income plan, value holdings, render report
```

The default provider is `auto`: **inline** when an agent drives it, otherwise `codex`
(or set `EPIPHANY_PROVIDER`). For the agent-driven path, `wrapper.run` does the bookends
(`prepare` seeds the run; the agent drives the graph via the harness CLI; `--finalize
<session_dir>` renders the charts/PDF).

**Your data persists across sessions** under `~/.epiphany-finance/users/<you>/` (survives clearing
the chat). To start over: `--reset` (this user) or `--reset-all` (everyone), `+ --yes` to skip the
confirm prompt. That is the only thing that erases saved data.

### Codex variant

To run the *same* skill under Codex/gpt-5.5 (a provider swap — no rebuild), install the provider
extra and deploy the Codex entry point into Codex's own skills dir:

```bash
pip install -e '~/projects/goatcs-harness[providers]'   # codex provider needs langchain-core
bash install-codex.sh                                    # deploys to ~/.codex/skills/epiphany-finance/
```

Then either ask Codex for finance help, or run `python3 -m wrapper.run --both --provider codex`.
Details + caveats: **`SKILL-CODEX.md`**.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: goatcs_harness` | runtime not installed/importable | `pip install -e ~/projects/goatcs-harness` or prepend `PYTHONPATH=~/projects/goatcs-harness` |
| PDF step fails on Linux | missing Pango libs | `sudo apt install libpango-1.0-0 libpangocairo-1.0-0` |
| quotes come back **offline / stale** | no network or Yahoo throttling | report still renders (degraded); HC-1 retries transient failures, then falls back to cache/offline |
| interpreter hangs after a chart render | wrong kaleido line in this env | keep `kaleido==0.2.1` for this skill (see §3 note) |
| `RuntimeError: no reasoning provider available` | headless run, no provider | run under the agent (inline), or set `EPIPHANY_PROVIDER` / install a provider |

---

## 7. What gets deployed

`install.sh` copies into `~/.claude/skills/epiphany-finance/`:

- `graph.json`, `SKILL.md`, `appendix.md`, `brief.md`, `pyproject.toml`, `install.sh`
- `modules/` (per-node reasoning contracts), `wrapper/` (Python), `fixtures/`, `tests/`

General guidance only — the skill does **not** pick stocks or compare specific securities,
and every report carries a mandatory disclaimer.

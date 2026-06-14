"""epiphany-finance CLI (IC-01: drives the graph via the goatcs_harness.run() public API, not a
subprocess). Handles intake, SQLite state, live quotes, and chart/PDF rendering AROUND the graph.

Provider model (build-plan fix B):
  • headless (codex / claude-cli): run() drives the graph end-to-end here, then we finalize.
  • inline (agent-driven): run.py does the BOOKENDS — `prepare` writes the seed; the driving agent
    (Claude Code) runs the graph via the harness CLI; then `--finalize <session_dir>` renders.
Default provider = auto (harness resolution: inline only when an agent drives, else codex/etc.).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:                                   # support both `python -m wrapper.run` and direct exec
    from . import charts, intake, pdf, quote, workspace
    from .disclaimer import disclaimer_for
    from .state import DEFAULT_DB, FinanceState
except ImportError:                    # pragma: no cover
    import charts, intake, pdf, quote, workspace     # type: ignore
    from disclaimer import disclaimer_for           # type: ignore
    from state import DEFAULT_DB, FinanceState      # type: ignore

DEFAULT_GRAPH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "graph.json")
DOC_TYPE = "Financial Analysis Report"


# ---------------------------------------------------------------- provider
def resolve_provider(requested: str) -> str:
    if requested and requested != "auto":
        return requested
    try:
        from goatcs_harness.providers import resolve_default_provider
        return resolve_default_provider()
    except Exception:
        if os.environ.get("CLAUDECODE") or os.environ.get("AI_AGENT"):
            return "inline"
        return "codex"


# ---------------------------------------------------------------- seed
def build_seed(fstate: dict, quote_data: dict, *, mode: str, markdown: bool, pdf_flag: bool,
               context_text: str, out_dir: str) -> dict:
    """Assemble the graph seed: financial_state + top-level flag signals (fix F) + quotes + paths."""
    return {
        "context_text": context_text,
        "financial_state": fstate,
        "mode": mode,
        "markdown_flag": bool(markdown),
        "pdf_flag": bool(pdf_flag),
        "doc_type": DOC_TYPE,
        "report_out_path": os.path.join(out_dir, "report.md"),
        "pdf_out_path": os.path.join(out_dir, "report.pdf"),
        "quote_data_seed": quote_data,
    }


def _fmt_shares(s) -> str:
    """Grouped share count — never scientific notation (audit: `{:g}` printed `1e+06`)."""
    try:
        v = float(s)
    except (TypeError, ValueError):
        return str(s)
    return f"{int(v):,}" if v == int(v) else f"{v:,.4f}".rstrip("0").rstrip(".")


def _money(x) -> str:
    """`$1,234.56` or `n/a` — thousands-grouped (printf `%` has no comma flag, hence a helper)."""
    return f"${x:,.2f}" if isinstance(x, (int, float)) else "n/a"


_BENEFIT_HINTS = ("ssi", "ssdi", "disability", "medicaid", "snap", "social security",
                  "supplemental security", "tanf", "section 8", "housing assistance")


def is_benefit_dependent(result_state: dict | None, fstate: dict | None) -> bool:
    """Robust, deterministic detection so the benefit-safety surfacing never depends on an LLM:
    the classifier flag, the dependency-flags dict, OR a means-tested income source by name."""
    rs = result_state or {}
    if rs.get("benefit_dependent"):
        return True
    flags = rs.get("benefit_dependency_flags") or {}
    if isinstance(flags, dict) and any(flags.get(k) for k in ("ssi", "ssdi", "medicaid", "snap")):
        return True
    for src in (fstate or {}).get("income_sources") or []:
        name = str(src.get("source_name") or "").lower()
        if any(h in name for h in _BENEFIT_HINTS):
            return True
    return False


_BENEFIT_SAFETY_BLOCK = (
    "## ⚠️ Benefit Safety (read this first)\n\n"
    "You depend on means-tested benefits, so protecting your eligibility comes BEFORE any "
    "saving or investing idea in this report:\n\n"
    "- **Asset limits:** SSI and Medicaid have low countable-resource limits, so simply saving more "
    "cash can reduce or suspend your benefits. Do not move money into savings/investments without "
    "checking the limit first.\n"
    "- **ABLE account:** if you became disabled before age 26, an ABLE account lets you save beyond "
    "those limits without losing eligibility — ask a benefits counselor whether you qualify.\n"
    "- **Earning more:** income limits and work incentives (e.g. SSDI's Trial Work Period) apply; "
    "report income changes to the SSA so a raise doesn't accidentally end a benefit.\n"
    "- **Verify first:** exact dollar thresholds vary by state and year. Confirm with the Social "
    "Security Administration (SSA), your state Medicaid/benefits office, or a FREE benefits "
    "counselor BEFORE moving money, saving more, or taking on work.\n")


def _benefit_safety_md(result_state: dict | None) -> str:
    """Deterministic benefit-safety section, optionally enriched with the graph's own
    `benefit_safety` notes when present (handles dict OR str output shapes)."""
    block = _BENEFIT_SAFETY_BLOCK
    bs = (result_state or {}).get("benefit_safety")
    extra = ""
    if isinstance(bs, str) and bs.strip():
        extra = bs.strip()
    elif isinstance(bs, dict):
        for k in ("note", "consult_note", "summary", "detail"):
            if isinstance(bs.get(k), str) and bs[k].strip():
                extra = bs[k].strip()
                break
    if extra and extra not in block:
        block += f"\n{extra}\n"
    return block


def _uncertain_appendix_md(result_state: dict | None) -> str:
    """Render an UNCERTAIN appendix from the ensemble's `challenge_list` so a disputed figure is
    SURFACED, never silently scrubbed (audit B2 — the appendix was a dead pipe). Tolerant of the
    LLM output shape (list of dicts or strings)."""
    cl = (result_state or {}).get("challenge_list")
    if not isinstance(cl, list) or not cl:
        return ""
    lines = ["## Appendix: Uncertain Figures", "",
             "The following figures could not be independently verified to quorum and should be "
             "treated as UNCERTAIN — verify them before relying on them:", ""]
    for item in cl:
        if isinstance(item, dict):
            fig = item.get("figure") or item.get("claim") or item.get("item") or ""
            why = item.get("issue") or item.get("reason") or item.get("note") or item.get("verdict") or ""
            lines.append(f"- {fig}{(' — ' + str(why)) if why else ''}".strip())
        elif str(item).strip():
            lines.append(f"- {str(item).strip()}")
    return "\n".join(lines) + "\n"


def _extract_summary(md: str) -> str:
    """Pull the plain-language 'What this means for you' section for the approval preview."""
    lines = (md or "").splitlines()
    for i, ln in enumerate(lines):
        if "what this means" in ln.lower() and ln.lstrip().startswith("#"):
            out = []
            for nxt in lines[i + 1:]:
                if nxt.lstrip().startswith("#") and out:
                    break
                out.append(nxt)
            return ("\n".join(out)).strip()[:700]
    return ""


# ---------------------------------------------------------------- finalize (shared)
def read_session_state(session_dir: str) -> dict:
    """Reconstruct the final graph state by merging every ACCEPTED node submission from the ledger
    (the harness records each node's committed outputs as ledger 'submission' entries)."""
    state: dict = {}
    ledger = os.path.join(session_dir, "ledger.jsonl")
    if os.path.exists(ledger):
        with open(ledger, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("verdict") == "accept" and isinstance(rec.get("submission"), dict):
                    state.update(rec["submission"])
    return state


_PROGRESS_LABELS = {"enter": "→ starting", "exit": "✓ finished"}


def render_progress(ev: dict, out=print) -> None:
    """HC-5 (finv2 S16/N-PROGRESS): render a structured on_progress event for the conversational
    front-end (plain language, non-blocking). The harness fires ordered {phase, node, route} events
    at node entry/exit; this turns them into a friendly one-liner and logs them for audit. Never
    alters routing or results — it is a pure side-effect channel."""
    phase = ev.get("phase")
    node = (ev.get("node") or "").replace("N-", "").replace("-", " ").title()
    label = _PROGRESS_LABELS.get(phase, phase)
    line = f"    {label}: {node}"
    if phase == "exit" and ev.get("route"):
        line += f"  → {ev['route'].replace('N-', '').replace('-', ' ').title()}"
    out(line)


def finalize(result_state: dict, *, out_dir: str, quote_data: dict, bracket: str | None,
             fstate: dict, db: FinanceState | None, markdown: bool, pdf_flag: bool,
             basename: str = "report", out=print) -> dict:
    """Shared post-graph step: render charts, assemble PDF, ensure verbatim disclaimer, persist.

    `basename` (no extension) names the dated/descriptive artifacts so reports are never overwritten:
    <out_dir>/<basename>.md, <basename>.pdf, and charts in <basename>-charts/."""
    os.makedirs(out_dir, exist_ok=True)
    report_md = result_state.get("report_markdown") or ""
    chart_specs = result_state.get("chart_specs") or []

    try:
        from . import finance as _fin
    except ImportError:                                 # pragma: no cover — script-mode fallback
        import finance as _fin                            # type: ignore

    # Defense-in-depth: the wrapper GUARANTEES the mandatory compliance elements regardless of what
    # the LLM node produced — verbatim disclaimer (fix C / V-FIN-01), a timestamped holdings table
    # (Q2 / V-FIN-21/22), the Data Freshness section (Q19/20), a DETERMINISTIC "Your Numbers" block
    # (Q2 audit-2026-06-14 — figures computed, not LLM-guessed), and a benefit-safety block.
    bd = is_benefit_dependent(result_state, fstate)

    # Deterministic "Your Numbers" — monthly income/expenses/surplus (every cadence normalized) +,
    # if there's a surplus, a clearly-(estimated) compound projection. These replace the figures the
    # LLM previously produced unverified.
    nums = _fin.monthly_numbers(fstate or {})
    if (nums["monthly_income"] or nums["monthly_expenses"]) and "## Your Numbers" not in report_md:
        s = nums["monthly_surplus"]
        cat = "".join(f"  - {c}: ${v:,.2f}/mo\n" for c, v in nums["expenses_by_category"].items())
        nb = ("\n## Your Numbers (calculated)\n\n"
              f"- **Monthly income:** ${nums['monthly_income']:,.2f}\n"
              f"- **Monthly expenses:** ${nums['monthly_expenses']:,.2f}\n" + (cat or "") +
              f"- **Monthly {'surplus' if s >= 0 else 'shortfall'}:** ${abs(s):,.2f}"
              f"{'' if s >= 0 else ' — expenses exceed income; the plan below focuses on closing this gap'}\n")
        if s > 0 and bd:
            # Benefit-dependent + surplus: do NOT show a rosy "invest it" projection that implicitly
            # encourages moving money past a means-tested asset limit. Point to the benefit-safe path.
            nb += (f"\nYou have about **${s:,.2f}/month** left over. Because you rely on means-tested "
                   "benefits, do **not** simply move it into savings or investments — that can push "
                   "you over an asset limit and reduce or end your benefits. See **Benefit Safety** "
                   "below for how to keep it safely (for example, an ABLE account).\n")
        elif s > 0:
            nb += ("\nIf you invested that surplus at an **(estimated)** 10%/yr index return "
                   "(7% after ~3% inflation), it could grow to:\n\n"
                   "| Years | Nominal | After inflation (real) |\n|---|---|---|\n")
            for r in _fin.projection_from_surplus(s):
                nb += f"| {r['years']} | ${r['nominal']:,.2f} | ${r['real']:,.2f} |\n"
            nb += "\nProjections are estimates, not guarantees — see the disclaimer.\n"
        report_md += nb

    holdings = (fstate or {}).get("portfolio_holdings") or []
    if holdings and quote_data and quote_data.get("prices"):
        val = _fin.portfolio_valuation(holdings, quote_data["prices"])
        rows = [f"| {h['ticker']} | {_fmt_shares(h['shares'])} | {_money(h['price'])} | "
                f"{_money(h['current_value'])} | {_money(h['gain_loss'])} | "
                f"{(h.get('source_ts') or 'unavailable')}"
                f"{' (cached)' if h.get('used_fallback') else ''} |" for h in val["holdings"]]
        notes = []
        if val.get("fallback_count"):
            notes.append(f"{val['fallback_count']} price(s) are cached/last-known, not live")
        if val.get("excluded_count"):
            notes.append(f"{val['excluded_count']} holding(s) are EXCLUDED from the totals — no "
                         "price available")
        caveat = (" " + "; ".join(notes) + ".") if notes else ""
        table = ("\n## Current Holdings (live valuation)\n\n"
                 "| Ticker | Shares | Price | Current Value | Gain/Loss | Market data (exact) |\n"
                 "|---|---|---|---|---|---|\n" + "\n".join(rows) +
                 f"\n\n**Total value: ${val['total_value']:,.2f}** "
                 f"(cost ${val['total_cost']:,.2f}; gain/loss ${val['total_gain']:,.2f}).{caveat} "
                 "Prices may be delayed — see Data Freshness.\n")
        if "Current Holdings (live valuation)" not in report_md:
            report_md += table

    # Benefit-safety: GUARANTEE the cliff/ABLE/consult block reaches a benefit-dependent user's
    # report (it was previously LLM-discretionary and could silently vanish — audit benefit#1).
    if bd and "Benefit Safety" not in report_md:
        report_md += "\n" + _benefit_safety_md(result_state)

    # UNCERTAIN appendix: surface any ensemble dissent deterministically (audit B2 — was a dead pipe).
    if "Appendix: Uncertain Figures" not in report_md:
        appendix = _uncertain_appendix_md(result_state)
        if appendix:
            report_md += "\n" + appendix

    if "## Data Freshness" not in report_md:
        report_md += "\n" + quote.data_freshness_section(quote_data)

    disc = disclaimer_for(bracket, benefit_dependent=bd)
    if not report_md.startswith(disc):
        report_md = f"{disc}\n\n{report_md}"
    if not report_md.rstrip().endswith(disc.rstrip()):
        report_md = f"{report_md}\n\n{disc}\n"

    # S17 defense-in-depth: run the FULL deterministic compliance battery over the finalized report
    # and warn loudly on every failure (audit Q1 — was disclaimer-only, so glossary/plain-summary/
    # no-stock-pick had no live backstop under the inline-collapsing LLM gate). LOG-ONLY: the report
    # still ships (operator chose warn-loud-still-ship); E27 owns any in-graph retry.
    try:
        from . import checks as _checks
    except ImportError:                                 # pragma: no cover — script-mode fallback
        import checks as _checks                         # type: ignore
    for _name, _ok, _msg in _checks.run_report_checks(report_md, quote_data):
        if not _ok:
            out(f"    ⚠ compliance: {_name} — {_msg}")

    out("  • Rendering charts…")
    render_result = charts.render_specs(chart_specs, os.path.join(out_dir, f"{basename}-charts"),
                                        quote_data)
    for sk in render_result["skipped"]:
        out(f"    – skipped: {sk['title']} ({sk['reason']})")

    outputs = {"skipped_charts": render_result["skipped"]}
    if markdown:
        md_path = os.path.join(out_dir, f"{basename}.md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(report_md)
        outputs["markdown_path"] = md_path
        out(f"  • Markdown report: {md_path}")
    if pdf_flag:
        out("  • Building PDF…")
        res = pdf.build_report_pdf(report_md, os.path.join(out_dir, f"{basename}.pdf"),
                                   render_result=render_result, document_type=DOC_TYPE)
        outputs["pdf_path"] = res.get("pdf_path")
        outputs["pdf_status"] = res.get("status")
        out(f"  • PDF: {res.get('pdf_path')} ({res.get('status')})")
    return outputs


# ---------------------------------------------------------------- prepare
def prepare(db: FinanceState, *, location: str | None, update: str | None,
            mode: str, markdown: bool, pdf_flag: bool, out_dir: str, out=print) -> dict:
    """Build everything the graph needs: ensure state, fetch quotes, assemble the seed."""
    fstate = db.export()
    if location:
        fstate.setdefault("profile", {})["location"] = location
    out("  • Fetching live quotes…")
    qd = quote.fetch_quotes(db.tickers(), db)
    for w in qd.get("warnings", []):
        out(f"    ! {w}")
    ctx = update or ""
    return build_seed(fstate, qd, mode=mode, markdown=markdown, pdf_flag=pdf_flag,
                      context_text=ctx, out_dir=out_dir)


# ---------------------------------------------------------------- reset
def _do_reset(args) -> int:
    """Wipe saved data and exit. `--reset-all` clears the entire store; `--reset` clears just the
    addressed user (--user, else the last-used one). Confirms first unless --yes. Destructive and
    irreversible — persistence is the default; this is the ONLY thing that erases it."""
    if args.reset_all:
        users = workspace.list_users()
        who = ", ".join(users) if users else "none"
        what = (f"EVERYTHING — all {len(users)} saved user(s) ({who}), the registry, and every "
                f"report/session under:\n  {workspace.ROOT}")
        slug = None
    else:
        slug = workspace.slugify(args.user) if args.user else workspace.last_user()
        if not slug or slug not in workspace.list_users():
            print("Nothing to reset — I don't have any saved data"
                  + (f" for '{slug}'." if slug else " yet."))
            return 0
        n = len(workspace.list_reports(slug))
        what = (f"the saved data for '{slug}' (your financial details, {n} report(s), and run "
                f"history) under:\n  {workspace.user_dir(slug)}")

    print(f"⚠️  This will permanently delete {what}\n   This cannot be undone.")
    if not args.yes:
        try:
            resp = input("   Type 'yes' to confirm (anything else cancels): ").strip().lower()
        except EOFError:
            resp = ""
        if resp not in ("y", "yes"):
            print("Cancelled — nothing was deleted.")
            return 0
    workspace.reset_all() if args.reset_all else workspace.reset_user(slug)
    print("✓ Done. Your saved data has been wiped. The next run starts fresh.")
    return 0


_PRIVACY_NOTE = ("I save everything locally and UNENCRYPTED (your details, reports, and run "
                 "history) here — it stays even if you clear the chat, and nothing is sent online "
                 "except live price lookups:\n  {dir}\n")


def _approval_gate(state: dict | None, *, yes: bool, out=print, inp=input) -> bool:
    """One-time plain-text plan approval before the report is written (Q4). Interactive only — a
    non-tty / --yes / scripted run auto-approves, so headless drives and tests are unaffected."""
    if yes or not sys.stdin.isatty():
        return True
    summary = _extract_summary((state or {}).get("report_markdown") or "")
    out("\n— Your plan is ready for your approval —")
    if summary:
        out(summary)
    try:
        resp = inp("\nSave this report? Type 'yes' to save, or tell me what to change: ").strip().lower()
    except EOFError:
        return True
    if resp in ("y", "yes", "ok", "okay", ""):
        return True
    out("Okay — not saved. Re-run when ready (e.g. `epiphany-finance --update \"<your change>\"`, "
        "or `epiphany-finance --mode intake` to adjust your details).")
    return False


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="epiphany-finance",
                                 description="Your friendly personal finance helper.")
    ap.add_argument("--mode", default="report",
                    choices=["intake", "analyze", "budget", "income", "portfolio", "report"])
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--both", action="store_true")
    ap.add_argument("--location")
    ap.add_argument("--update", help="record a transaction / add context text")
    ap.add_argument("--user", help="which person's saved data to use (name or slug)")
    ap.add_argument("--db", default=DEFAULT_DB, help="override DB path (advanced/tests)")
    ap.add_argument("--provider", default="auto",
                    choices=["auto", "inline", "codex", "claude-cli"])
    ap.add_argument("--graph", default=DEFAULT_GRAPH)
    ap.add_argument("--out", help="override reports dir (advanced/tests)")
    ap.add_argument("--finalize", metavar="SESSION_DIR",
                    help="(inline) render a report from a completed harness session")
    ap.add_argument("--reset", action="store_true",
                    help="permanently wipe THIS user's saved data, then exit (asks to confirm)")
    ap.add_argument("--reset-all", action="store_true",
                    help="permanently wipe ALL saved users / the entire store, then exit")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="skip the confirmation prompt (for scripted / headless runs)")
    args = ap.parse_args(argv)

    # ---- reset: destructive; runs BEFORE any workspace/intake work and always exits ----
    if args.reset or args.reset_all:
        return _do_reset(args)

    markdown = args.markdown or args.both or not args.pdf      # default: markdown on
    pdf_flag = args.pdf or args.both

    # ---- resolve the per-user workspace (all data persists here across sessions) ----
    explicit_db = args.db != DEFAULT_DB
    slug = workspace.slugify(args.user) if args.user else workspace.last_user()
    need_intake = (args.mode == "intake" or (argv is None and len(sys.argv) == 1)
                   or (slug is None and not explicit_db))

    try:
        # New/returning user + DB resolution
        if explicit_db:
            slug = slug or "default"
            dbp = args.db
            workspace.ensure_user(slug)
        elif need_intake and slug is None:
            # brand-new user: collect name+data first, then place their folder
            print("Welcome! Let's set up your finances. A few quick questions:")
            fstate = intake.run_intake()
            slug = workspace.slugify(args.user or (fstate.get("profile") or {}).get("name"))
            slug = workspace.ensure_user(slug, name=(fstate.get("profile") or {}).get("name"))
            dbp = workspace.db_path(slug)
            print("\n" + _PRIVACY_NOTE.format(dir=workspace.user_dir(slug)))
            with FinanceState(dbp) as db:
                db.import_state(fstate)
                if args.mode == "intake":
                    print("\n✓ All set. Run `epiphany-finance` any time for an updated report.")
                    return 0
            need_intake = False
        else:
            slug = workspace.ensure_user(slug or "default")
            dbp = workspace.db_path(slug)

        out_dir = args.out or workspace.reports_dir(slug)
        os.makedirs(out_dir, exist_ok=True)

        with FinanceState(dbp) as db:
            if need_intake and (db.is_empty() or args.mode == "intake"):
                print("Let's (re)enter your details. A few quick questions:")
                fstate = intake.run_intake()
                if args.user is None and (fstate.get("profile") or {}).get("name"):
                    slug = workspace.ensure_user(slug, name=fstate["profile"]["name"])
                db.import_state(fstate)
                if args.mode == "intake":
                    print("\n" + _PRIVACY_NOTE.format(dir=workspace.user_dir(slug)))
                    print(f"✓ Saved to {workspace.user_dir(slug)}")
                    return 0

            bracket = (db.export().get("profile") or {}).get("wealth_bracket")
            provider = resolve_provider(args.provider)
            basename = workspace.report_basename(args.mode)
            print(f"\nGenerating your report for '{slug}' (provider: {provider})…")

            if args.finalize:
                qd = quote.fetch_quotes(db.tickers(), db)
                state = read_session_state(args.finalize)
                if not _approval_gate(state, yes=args.yes):
                    return 0
                outs = finalize(state, out_dir=out_dir, quote_data=qd, bracket=bracket,
                                fstate=db.export(), db=db, markdown=markdown, pdf_flag=pdf_flag,
                                basename=basename)
                print(f"\n✓ Done. Saved in: {out_dir}")
                return 0

            seed = prepare(db, location=args.location, update=args.update, mode=args.mode,
                           markdown=markdown, pdf_flag=pdf_flag, out_dir=out_dir)
            session_dir = os.path.join(workspace.sessions_dir(slug), basename)
            seed_path = os.path.join(session_dir, "seed.json")
            os.makedirs(session_dir, exist_ok=True)
            with open(seed_path, "w", encoding="utf-8") as fh:
                json.dump(seed, fh, indent=2)

            if provider == "inline":
                print(
                    "\nThis skill reasons through your finances with an AI agent (Claude Code).\n"
                    "Claude Code drives the analysis graph, then I build your report.\n"
                    f"  graph: {args.graph}\n  seed:  {seed_path}\n"
                    f"  drive: goatcs-harness run {args.graph} --seed {seed_path} "
                    f"--provider inline --scratch-dir {session_dir}/run\n"
                    f"  then:  epiphany-finance --user {slug} --finalize {session_dir}/run --both\n")
                return 0

            from goatcs_harness import run as _run
            print("  • Reasoning through your finances (this can take a minute)…")
            result = _run(args.graph, seed=seed, provider=provider,
                          on_progress=render_progress,            # HC-5: structured progress narration
                          out_dir=out_dir, scratch_dir=os.path.join(session_dir, "run"),
                          allow_network=True)
            state = getattr(result, "state", None) or read_session_state(
                os.path.join(session_dir, "run"))
            qd = seed["quote_data_seed"]
            if not _approval_gate(state, yes=args.yes):
                return 0
            outs = finalize(state, out_dir=out_dir, quote_data=qd, bracket=bracket,
                            fstate=db.export(), db=db, markdown=markdown, pdf_flag=pdf_flag,
                            basename=basename)
            print(f"\n✓ Done. Saved in: {out_dir}\n  {outs.get('markdown_path','')}")
            return 0
    except KeyboardInterrupt:
        print("\nCancelled — nothing was lost; your data is saved.")
        return 130
    except Exception as ex:                              # friendly, never a raw traceback (Q7)
        print(f"\nSomething went wrong: {ex}\n"
              "Your saved data is safe. Try again, or run with --mode intake to re-enter details.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

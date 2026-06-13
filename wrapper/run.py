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

    # Defense-in-depth: the wrapper GUARANTEES the mandatory compliance elements regardless of what
    # the LLM node produced — verbatim disclaimer (fix C / V-FIN-01), a timestamped holdings table
    # (Q2 / V-FIN-21/22), and the Data Freshness section (Q19/20).
    holdings = (fstate or {}).get("portfolio_holdings") or []
    if holdings and quote_data and quote_data.get("prices"):
        from . import finance as _fin
        val = _fin.portfolio_valuation(holdings, quote_data["prices"])
        rows = [f"| {h['ticker']} | {h['shares']:g} | "
                f"{('$%.2f' % h['price']) if h['price'] is not None else 'n/a'} | "
                f"{('$%.2f' % h['current_value']) if h['current_value'] is not None else 'n/a'} | "
                f"{('$%.2f' % h['gain_loss']) if h['gain_loss'] is not None else 'n/a'} | "
                f"{h.get('source_ts') or 'n/a'} |" for h in val["holdings"]]
        table = ("\n## Current Holdings (live valuation)\n\n"
                 "| Ticker | Shares | Price | Current Value | Gain/Loss | Market data (exact) |\n"
                 "|---|---|---|---|---|---|\n" + "\n".join(rows) +
                 f"\n\n**Total value: ${val['total_value']:,.2f}** "
                 f"(cost ${val['total_cost']:,.2f}; gain/loss ${val['total_gain']:,.2f}). "
                 "Prices may be delayed — see Data Freshness.\n")
        if "Current Holdings (live valuation)" not in report_md:
            report_md += table

    if "## Data Freshness" not in report_md:
        report_md += "\n" + quote.data_freshness_section(quote_data)

    disc = disclaimer_for(bracket)
    if not report_md.startswith(disc):
        report_md = f"{disc}\n\n{report_md}"
    if not report_md.rstrip().endswith(disc.rstrip()):
        report_md = f"{report_md}\n\n{disc}\n"

    # S17 defense-in-depth: a single deterministic compliance assertion over the finalized report
    # (verbatim disclaimer present top+bottom). This is the live-path use of wrapper.checks; it is a
    # LOG-ONLY guard, NOT a routing or quality-RETRY authority (E27 owns retry — no re-drive here).
    try:
        from . import checks as _checks
    except ImportError:                                 # pragma: no cover — script-mode fallback
        import checks as _checks                         # type: ignore
    _disc_ok, _disc_msg = _checks.disclaimer_top_and_bottom(report_md)
    if not _disc_ok:
        out(f"    ⚠ compliance: disclaimer — {_disc_msg}")

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
            print(f"\nI'll save everything locally (unencrypted) here — it stays even if you clear "
                  f"the chat session:\n  {workspace.user_dir(slug)}\n")
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
                    print(f"\n✓ Saved to {workspace.user_dir(slug)}")
                    return 0

            bracket = (db.export().get("profile") or {}).get("wealth_bracket")
            provider = resolve_provider(args.provider)
            basename = workspace.report_basename(args.mode)
            print(f"\nGenerating your report for '{slug}' (provider: {provider})…")

            if args.finalize:
                qd = quote.fetch_quotes(db.tickers(), db)
                state = read_session_state(args.finalize)
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

"""V-FIN-27 / Q6 — feature integration: no produced-but-unread signal (beyond terminal sinks),
every CLI flag/mode/provider maps to real behavior, optional features bypass without deadlock.
"""
import os
import re

from conftest import GRAPH

from goatcs_harness.loader import load


def _signals_in_condition(cond):
    if not cond:
        return set()
    toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", cond)
    kw = {"AND", "OR", "NOT", "IN", "PRESENT", "true", "false", "null"}
    return {t.split(".")[0] for t in toks if t not in kw}


def test_no_dead_signals_except_terminal_sinks():
    g = load(GRAPH)
    produced, read = set(), set()
    for n in g.nodes.values():
        produced |= set(n.write_keys)
        read |= set(n.read_keys)
    for e in g.edges:
        if e.signal_field:
            read.add(e.signal_field)
        read |= _signals_in_condition(e.gate_condition)
    # terminal sink tool outputs are allowed to be unread. v2 adds N-REFUSE (early_exit terminal):
    # `refusal_message` is a terminal-sink output with no downstream consumer (the run refuses there).
    allowed_dead = {"written_path", "pdf_path", "pdf_status", "refusal_message"}
    dead = produced - read - allowed_dead
    assert not dead, f"unexpected dead signals: {dead}"


def test_every_provider_resolves():
    import wrapper.run as run
    for p in ("inline", "codex", "claude-cli"):
        assert run.resolve_provider(p) == p
    # auto resolves to *something* concrete
    assert run.resolve_provider("auto") in ("inline", "codex", "claude-cli", "ollama")


def test_every_cli_flag_present():
    import wrapper.run as run
    # build the parser and assert each documented option exists
    import argparse
    parser_opts = set()
    orig = argparse.ArgumentParser.add_argument

    def spy(self, *a, **k):
        for x in a:
            if isinstance(x, str) and x.startswith("--"):
                parser_opts.add(x)
        return orig(self, *a, **k)

    argparse.ArgumentParser.add_argument = spy
    try:
        try:
            run.main(["--help"])
        except SystemExit:
            pass
    finally:
        argparse.ArgumentParser.add_argument = orig
    for opt in ("--mode", "--markdown", "--pdf", "--both", "--location", "--update", "--db",
                "--provider", "--graph", "--out", "--finalize"):
        assert opt in parser_opts, f"missing CLI flag {opt}"


def test_optional_features_no_deadlock_via_fanout_regions():
    """No-deadlock is realized by 3 split_from fan-out regions (harness-chained AND-joins) +
    self-gating optional nodes — not gate-open/bypass edges. Verify detects all 3 regions and the
    conditional branches are flagged conditional (they emit null when their flag is false)."""
    from goatcs_harness import parallel
    g = load(GRAPH)
    regions = parallel.detect_regions(g)
    joins = {r.join for r in regions}
    # v2 adds the strategy fan-out region (N-STRATEGY-MERGE) on top of the carried v1 three.
    assert joins == {"N-RESEARCH-AGG", "N-SYNTHESIS-AGG", "N-REPORT", "N-STRATEGY-MERGE"}
    # the optional branches that must self-gate are present + marked conditional
    for n in ("N-RESEARCH-LOC", "N-RESEARCH-MKT", "N-QUOTE-FETCHER", "N-PORTFOLIO-ENGINE"):
        assert g.nodes[n].conditional, f"{n} must be conditional (self-gating)"
    # every fan-out branch reconverges on its AND-join (no orphan branch -> no deadlock)
    for r in regions:
        assert g.nodes[r.join].join_policy == "AND"
        assert len(r.branches) >= 2

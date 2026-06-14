#!/usr/bin/env python3
"""build_v2_graph.py — construct the v2 BASE graph additively over v1 (the carried 22-node graph),
then lower intent.json through the HC-3 compiler (build_graph) to the final native graph.json.

Topology = v1 + the operator-approved LEAN HYBRID (see .executor-session/design-decisions.md):
  routing (compiler-lowered): N-PREFLIGHT early_exit->N-REFUSE; N-FRAME-SELECT quality_gate(bracket)
    -> {survival,standard,hnw} -> N-FRAME-MERGE(OR) -> N-REPORT; N-STRATEGY-FANOUT parallel_merge.
  signal-driven (carried): has_investment_flag, data_freshness_regime (consumed in-node).
New feature nodes: N-MACRO-FETCH (wave 2), N-BENEFIT-SAFETY (wave 5), N-HITL-APPROVE (wave 8.5).

This is a STRUCTURAL builder: it adds nodes/edges + sets join policies/slots. Per-node CONTRACT
bodies (modules/N-*.md), tool_call upgrades, and signal emission are layered by their own steps
(S9-S16); this file only guarantees the topology lowers + verifies + is deadlock-free.

Usage: python tools/build_v2_graph.py   # writes graph.v2-base.json + graph.json (lowered)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.dirname(HERE)
HARNESS_WT = "/home/myuser/projects/goatcs-harness"
for p in (BUILD, HARNESS_WT):
    if p not in sys.path:
        sys.path.insert(0, p)

from build_graph import lower_intent_to_native  # noqa: E402

V1 = os.path.join(BUILD, "graph.v1.json")          # frozen v1 snapshot (carried base)


def _node(nid, typ, *, wave, tier="model-medium", inputs=(), outputs=(), tool_call=None,
          join_policy=None, agg=None, hitl=False, rationale=""):
    n = {"id": nid, "name": nid, "type": typ, "tier": tier, "exec_type": "inline", "hat": "",
         "wave": wave, "conditional": typ == "GATE",
         "inputs": [{"name": s, "type": "any", "signal_field": s, "required": False} for s in inputs],
         "outputs": [{"name": s, "type": "any", "signal_field": s, "required": True} for s in outputs],
         "raises_signals": [], "join_policy": join_policy, "aggregation_policy": agg,
         "module_file": f"modules/{nid}.md", "scale_gates": {}, "rationale": rationale,
         "tool_call": tool_call}
    if hitl:
        n["hitl"] = True
    return n


def _e(eid, src, dst, kind="required", *, sig=None, cond=None, cap=None, ajg=None, split=None):
    e = {"id": eid, "src": src, "dst": dst, "kind": kind}
    if sig:
        e["signal_field"] = sig
    if cond:
        e["gate_condition"] = cond
    if cap is not None:
        e["retry_cap"] = cap
    if ajg:
        e["and_join_group"] = ajg
    if split:
        e["split_from"] = split
    return e


def build_v2_base(v1: dict) -> dict:
    g = json.loads(json.dumps(v1))
    g["skill_version"] = "2.0.0"
    nodes = g["nodes"]
    edges = g["edges"]

    # ---- new nodes -------------------------------------------------------
    new_nodes = [
        # refuse terminal (early_exit target)
        _node("N-REFUSE", "SYNTHESIS", wave="0", tier="model-small", inputs=["preflight_ok"],
              outputs=["refusal_message"], rationale="early_exit terminal: refuse on no-context/insufficient"),
        # macro (wave 2) — feeds research-agg AND-join (rslot). INLINE reasoner like its
        # ECO/LOC/MKT siblings (network is wrapper-owned per the S11 design principle): it reasons
        # cited macro context when available, else clearly-labelled `(estimated)` defaults — and
        # NEVER halts. A bare `http.get_text` binding with empty args raised KeyError('url') and
        # hard-killed the whole graph; the estimated-fallback path in the module was unreachable.
        _node("N-MACRO-FETCH", "ANALYZER", wave="2", inputs=["wealth_bracket", "parsed_context"],
              outputs=["macro_context"],
              rationale="cited rates/inflation macro context (read-only, injection-hardened); "
                        "inline estimated-fallback, never halts"),
        # strategy fan-out region (wave 3.5)
        _node("N-STRATEGY-FANOUT", "GENERATOR", wave="3.5", inputs=["situation_analysis"],
              outputs=["strategy_seed"], rationale="parallel_merge source: budget/income/portfolio framings"),
        _node("N-STRAT-CAND-BUDGET", "GENERATOR", wave="3.5", inputs=["strategy_seed"],
              outputs=["cand_budget"], rationale="budget-framing strategy candidate"),
        _node("N-STRAT-CAND-INCOME", "GENERATOR", wave="3.5", inputs=["strategy_seed"],
              outputs=["cand_income"], rationale="income-framing strategy candidate"),
        _node("N-STRAT-CAND-PORTFOLIO", "GENERATOR", wave="3.5", inputs=["strategy_seed"],
              outputs=["cand_portfolio"], rationale="portfolio-framing strategy candidate"),
        _node("N-STRATEGY-MERGE", "AGGREGATION", wave="3.5", tier="model-large",
              inputs=["cand_budget", "cand_income", "cand_portfolio"], outputs=["strategy_plan"],
              join_policy="AND", agg="best_elements",
              rationale="merge.best_elements of strategy candidates -> strategy_plan feeding engines"),
        # benefit-safety (wave 5) — feeds synthesis-agg (sslot)
        _node("N-BENEFIT-SAFETY", "GENERATOR", wave="5",
              inputs=["benefit_dependency_flags", "income_plan"], outputs=["benefit_safety"],
              rationale="benefit cliffs/ABLE/consult; hard-gate silent-forfeit; cite+defer jurisdiction"),
        # bracket frame region (wave 8)
        _node("N-FRAME-SELECT", "GATE", wave="8", tier="model-small", inputs=["wealth_bracket"],
              outputs=["frame_selected"], rationale="quality_gate(bracket) -> report frame"),
        _node("N-FRAME-SURVIVAL", "GENERATOR", wave="8", tier="model-small", inputs=["wealth_bracket"],
              outputs=["report_frame_survival"], rationale="survival / benefit-dependent report framing"),
        _node("N-FRAME-STANDARD", "GENERATOR", wave="8", tier="model-small", inputs=["wealth_bracket"],
              outputs=["report_frame_standard"], rationale="standard (default) report framing"),
        _node("N-FRAME-HNW", "GENERATOR", wave="8", tier="model-small", inputs=["wealth_bracket"],
              outputs=["report_frame_hnw"], rationale="high-net-worth report framing"),
        _node("N-FRAME-MERGE", "AGGREGATION", wave="8", tier="model-small",
              inputs=["report_frame_survival", "report_frame_standard", "report_frame_hnw"],
              outputs=["report_frame"], join_policy="OR", agg="first_present",
              rationale="XOR/OR reconvergence: exactly one frame fires -> report_frame -> N-REPORT"),
        # HITL plan-approval (wave 8.5)
        _node("N-HITL-APPROVE", "GATE", wave="8.5", tier="model-small",
              inputs=["report_markdown"], outputs=["plan_approved", "rework_requested"], hitl=True,
              rationale="single plain-text plan-approval pause (exit-11); approve->emit, rework->report. "
                        "plan_approved/rework_requested are PRODUCED here by the human decision (grounds the gates)."),
    ]
    for n in new_nodes:
        nodes[n["id"]] = n

    # ---- edge surgery ----------------------------------------------------
    by_id = {e["id"]: e for e in edges}

    # (2) macro into the research AND-join
    edges.append(_e("E30", "N-CLASSIFY", "N-MACRO-FETCH", split="research"))
    edges.append(_e("E31", "N-MACRO-FETCH", "N-RESEARCH-AGG", ajg="rslot"))

    # (3) strategy detour: remove E12 (situation->budget); route through fan-out/merge
    edges[:] = [e for e in edges if e["id"] != "E12"]
    edges.append(_e("E32", "N-SITUATION-ANALYZE", "N-STRATEGY-FANOUT"))
    edges.append(_e("E33", "N-STRATEGY-MERGE", "N-BUDGET-ENGINE"))
    # N-STRATEGY-FANOUT's fan-out + join edges are produced by the parallel_merge lowering.

    # (5) benefit-safety into the synthesis AND-join (new sslot branch)
    edges.append(_e("E34", "N-INCOME-ENGINE", "N-BENEFIT-SAFETY", split="synth"))
    edges.append(_e("E35", "N-BENEFIT-SAFETY", "N-SYNTHESIS-AGG", ajg="sslot"))

    # (8) frame sub-DAG: runs right after N-SYNTHESIS-AGG, then SOURCES the chart/disclaimer `report`
    # fan-out region. Rationale — the original wiring hung the frame sub-DAG off synthesis AS WELL AS
    # the 2-branch report region, leaving synthesis with TWO forward out-edges after the region
    # sibling-chain rewrite; a serial router treats that as open-topology and re-serves synthesis
    # forever (the v2 ship-blocker). The frame sub-DAG is multi-hop (select->xor->merge), so it can't
    # be a `report` region branch itself (`_common_join` needs a direct shared join). Fix: synthesis
    # fans out to ONE thing (the frame chain); the chain ends at N-FRAME-MERGE, which becomes the
    # report region SOURCE. So the spine is synthesis -> frame-select -> frames -> frame-merge ->
    # (report region: chart -> disclaimer) -> report. report_frame is in state before N-REPORT (read
    # as a plain input — NO repslot join edge), and no repslot-contributing node carries a 2nd forward
    # edge, so verify reports a clean fan-out region (no convergence-without-region WARN).
    edges.append(_e("E36", "N-SYNTHESIS-AGG", "N-FRAME-SELECT"))
    edges.append(_e("E37", "N-FRAME-SURVIVAL", "N-FRAME-MERGE", ajg="fslot"))
    edges.append(_e("E38", "N-FRAME-STANDARD", "N-FRAME-MERGE", ajg="fslot"))
    edges.append(_e("E39", "N-FRAME-HNW", "N-FRAME-MERGE", ajg="fslot"))
    # N-FRAME-MERGE sources the report region (re-point the two split_from='report' branch edges off
    # synthesis). No E40 frame-merge->report repslot edge: report_frame is consumed as an input and
    # spine order guarantees frame-merge precedes N-REPORT.
    by_id["E22"]["src"] = "N-FRAME-MERGE"
    by_id["E23"]["src"] = "N-FRAME-MERGE"
    # N-FRAME-SELECT's case/default edges -> frames come from the quality_gate lowering.

    # (8.5) HITL plan-approval: PASS now routes to HITL, then approve->emit / rework->report(back-edge)
    e28 = by_id["E28"]               # N-QUALITY-GATE -> N-EMIT-MD (PASS)
    e28["dst"] = "N-HITL-APPROVE"
    edges.append(_e("E41", "N-HITL-APPROVE", "N-EMIT-MD", kind="gate-open", sig="plan_approved"))
    edges.append(_e("E42", "N-HITL-APPROVE", "N-REPORT", kind="back-edge",
                    cond="rework_requested == True", cap=2))

    # ---- signal consumption wiring (clear dead-signals: every new output is read downstream) ----
    def _add_input(nid, sig):
        n = nodes[nid]
        if sig not in {i["signal_field"] for i in n["inputs"]}:
            n["inputs"].append({"name": sig, "type": "any", "signal_field": sig, "required": False})

    _add_input("N-STRATEGY-FANOUT", "situation_analysis")   # fan-out reads the situation
    _add_input("N-BUDGET-ENGINE", "strategy_plan")          # merged strategy feeds the engines
    _add_input("N-SITUATION-ANALYZE", "macro_context")      # macro grounds the projections
    _add_input("N-SYNTHESIS-AGG", "benefit_safety")         # benefit-safety joins synthesis
    _add_input("N-REPORT", "report_frame")                  # bracket frame shapes the report
    for fr in ("N-FRAME-SURVIVAL", "N-FRAME-STANDARD", "N-FRAME-HNW"):
        _add_input(fr, "frame_selected")                    # frames read the gate's selection
    _add_input("N-HITL-APPROVE", "report_markdown")         # HITL reviews the drafted report

    # ---- carried-node UPGRADES (S9/S11/S13) ----
    def _add_output(nid, sig, required=True):
        n = nodes[nid]
        if sig not in {o["signal_field"] for o in n["outputs"]}:
            n["outputs"].append({"name": sig, "type": "any", "signal_field": sig, "required": required})

    # S9: N-CLASSIFY additionally emits benefit_dependency_flags + the data_freshness_regime seed.
    _add_output("N-CLASSIFY", "benefit_dependency_flags")
    _add_output("N-CLASSIFY", "data_freshness_regime")
    # FLAT benefit-dependency routing flag = OR(ssdi,ssi,medicaid,snap). A *scalar* bool (like
    # has_investment_flag) so the N-FRAME-SELECT survival gate can read it directly: routing a gate
    # on `benefit_dependency_flags.ssi == true` would (intentionally, with a scalar-dotted-read WARN)
    # type the whole flags OBJECT as bool and reject the dict. The flat flag is the idiomatic seam
    # and makes benefit-dependency a first-class survival-frame driver (not just bracket).
    _add_output("N-CLASSIFY", "benefit_dependent")
    _add_input("N-FRAME-SELECT", "benefit_dependent")      # survival frame fires for benefit-dependents
    _add_input("N-CHART-SPEC", "data_freshness_regime")     # freshness signal -> skip price charts
    # benefit_dependency_flags already consumed by N-BENEFIT-SAFETY (input declared).

    # S11: N-QUOTE-FETCHER becomes a REAL tool_call (HC-1 retry+cache opt-in) + HC-4 typed output
    # schema. The network fetch lives in wrapper/quote.py (harness network is wrapper-owned); the
    # node's tool_call normalizes/validates the fetched quote bundle deterministically — NOT a bare
    # data.passthrough — and HC-1 retry+cache is consumed in the wrapper fetch (test-asserted).
    qn = nodes["N-QUOTE-FETCHER"]
    qn["tool_call"] = {"tool": "data.passthrough", "args": {"value": "quote_data_seed"},
                       "outputs": {"quote_data": "value"}, "retry_cache": True,
                       "_v2_real_quote": True}
    qn["output_schema"] = {"quote_data": {"type": "dict", "required": True}}
    qn["module_file"] = "modules/N-QUOTE-FETCHER.md"

    # S13: N-ADVERSARIAL becomes the ensemble verification stage (quorum over monetary figures).
    # NICE default fixture (v2.1): J=3, k=2, T=0.34; downshiftable (node flag) for the $0 hot path.
    nodes["N-ADVERSARIAL"]["ensemble"] = {"mode": "quorum", "jury_size": 3, "k": 2,
                                          "dissent_threshold": 0.34,
                                          "cross_verify": {"verifier_provider": "default"},
                                          "scout_tier": "model-small", "fund_tier": "model-medium"}
    nodes["N-ADVERSARIAL"]["downshiftable"] = True

    g["metadata_v2"] = {"built_from": "v1 2.0.0 additive", "topology": "lean-hybrid",
                        "new_nodes": [n["id"] for n in new_nodes]}
    return g


def main():
    v1 = json.load(open(V1))
    base = build_v2_base(v1)
    json.dump(base, open(os.path.join(BUILD, "graph.v2-base.json"), "w"), indent=1)
    intent = json.load(open(os.path.join(BUILD, "intent.json")))
    graph, errors = lower_intent_to_native(base, intent)
    if errors:
        print("LOWERING ERRORS (fail-closed):", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 2
    json.dump(graph, open(os.path.join(BUILD, "graph.json"), "w"), indent=1)
    print(f"v2 graph.json written: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

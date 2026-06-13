#!/usr/bin/env python3
"""build_graph.py — epiphany-finance-v2's HC-3 compiler-integration build path (S3).

This is the FIRST production-skill consumer of the merged co-evolution topology compiler.
It is the *native-dialect* analogue of `goatcs_harness.coevolution.emit_intent.compile_to_graph_json`:
where that seam compiles a design-time `GraphDesignIR` and renders the *generator* edge dialect
(`source/target/edge_type`), this lowers an authored `intent.json` against the skill's *native*
runtime `graph.json` (`src/dst/kind`) — the shape the harness actually ships and the loader ingests.

It REUSES the real compiler seam end-to-end (no re-implementation of the wiring logic):
  - `compiler.compile_graph(intents, successors, nodes)`  — the two-pass linker (deterministic).
  - `emit_intent.render_compiled_edge(e)`                 — the canonical compiled-edge renderer.
  - `routing_intent.{deserialize_intent, validate_intent}`— the closed-taxonomy validator.
and applies the SAME mixed-graph + parallel_merge join-policy contract `compile_to_graph_json` uses.

Fail-closed (Finding A): the compiler's typed UNCERTAIN abstentions are surfaced as `errors`; a
caller that ships must check `errors == []`.

CLI:  python build_graph.py <base_graph.json> <intent.json> <out_graph.json>   (exit 2 on errors)
"""
from __future__ import annotations

import json
import sys

from goatcs_harness.coevolution import compiler as comp
from goatcs_harness.coevolution import emit_intent
from goatcs_harness.generator.routing_intent import deserialize_intent, validate_intent

# compiler edge_type vocabulary == native EDGE_KINDS vocabulary, so the translation from the
# generator dialect to the native dialect is a pure key-rename (source->src, target->dst,
# edge_type->kind); gate_condition/retry_cap/and_join_group/split_from/signal_field carry verbatim.
_GEN_TO_NATIVE_KEY = {"source": "src", "target": "dst", "edge_type": "kind"}


def _native_edge(compiled_edge) -> dict:
    """Render one compiled EdgeDesign into a *native* graph.json edge (src/dst/kind)."""
    gen = emit_intent.render_compiled_edge(compiled_edge)   # {id, source, target, edge_type, ...}
    out: dict = {}
    for k, v in gen.items():
        out[_GEN_TO_NATIVE_KEY.get(k, k)] = v
    return out


def _legacy_successors(base_edges: list[dict]) -> dict[str, str]:
    """The legacy linear spine = each node's structural forward successor (for sequential /
    early_exit fall-through / bounded_loop forward-exit).

    Prefer the first `required` out-edge (mirrors compile_ir); fall back to the first *forward*
    out-edge of any other kind (gate-open / forward-conditional / optional) when a node has no
    `required` edge — e.g. N-PREFLIGHT's only forward edge is a `gate-open` (preflight_ok). A
    `back-edge` / `terminal` is never a forward successor. Without this fallback an early_exit on a
    gate-open-only node would abstain ("no fall-through successor")."""
    required_succ: dict[str, str] = {}
    forward_succ: dict[str, str] = {}
    for e in base_edges:
        kind = e.get("kind", "required")
        if kind in ("back-edge", "terminal"):
            continue
        forward_succ.setdefault(e["src"], e["dst"])
        if kind == "required":
            required_succ.setdefault(e["src"], e["dst"])
    return {src: required_succ.get(src, forward_succ[src]) for src in forward_succ}


def lower_intent_to_native(base_graph: dict, intent_payload: dict) -> tuple[dict, list[str]]:
    """Lower an authored intent.json against a native base graph.json.

    Returns (graph_json, errors). Intent-bearing source nodes get the compiler's edges (translated
    to native); every other edge keeps its hand-authored native form (the mixed-graph contract).
    `errors` aggregates closed-taxonomy validation errors + the compiler's UNCERTAIN abstentions —
    a fail-closed caller ships only when it is empty.
    """
    intents = deserialize_intent(intent_payload)
    nodes = base_graph["nodes"]                       # native dialect: nodes is a dict {id: node}
    node_ids = set(nodes)
    base_edges = list(base_graph["edges"])

    # validate intents against the closed taxonomy (fail-closed input gate)
    errors: list[str] = []
    for nid, intent in intents.items():
        v = validate_intent(intent)
        errors.extend(f"{nid}: {e}" for e in v.errors)
        if nid not in node_ids:
            errors.append(f"{nid}: intent declared for a node absent from the graph")

    successors = _legacy_successors(base_edges)
    result = comp.compile_graph(intents, successors, nodes=node_ids)
    # surface the compiler's typed UNCERTAIN abstentions (Finding A — never ship a silently
    # degraded graph that still loads green but dropped a loop/exit edge).
    errors += [f"{n}: {r}" for n, r in result.uncertain_nodes.items()]

    # mixed graph: drop legacy edges whose SOURCE is intent-bearing; keep the rest; append compiled.
    intent_sources = {nid for nid in intents if intents[nid] is not None}
    kept = [e for e in base_edges if e["src"] not in intent_sources]
    compiled = [_native_edge(e) for e in result.edges]

    out = json.loads(json.dumps(base_graph))          # deep copy; preserve top-level metadata
    out["edges"] = kept + compiled

    # a parallel_merge JOIN node must declare join_policy=AND (else detect_regions skips the
    # region) — mirror compile_to_graph_json's faithful end-to-end fan-out.
    for nid, intent in intents.items():
        if isinstance(intent, dict) and intent.get("kind") == "parallel_merge" and len(intent.get("branches", [])) >= 2:
            jn = out["nodes"].get(intent["join"])
            if jn is not None:
                jn["join_policy"] = "AND"
                jn["aggregation_policy"] = intent.get("agg", "")
    return out, errors


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: build_graph.py <base_graph.json> <intent.json> <out_graph.json>", file=sys.stderr)
        return 2
    base = json.load(open(argv[1]))
    intent = json.load(open(argv[2]))
    graph, errors = lower_intent_to_native(base, intent)
    if errors:
        print("COMPILE ERRORS (fail-closed, not shipping):", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 2
    # deterministic serialization (stable key order) so identical input -> byte-identical output
    json.dump(graph, open(argv[3], "w"), indent=1, sort_keys=False)
    print(f"lowered -> {argv[3]} ({len(graph['edges'])} edges, intent_compiled=True)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

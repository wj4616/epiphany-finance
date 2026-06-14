"""Render chart_specs to PNG via Plotly + Kaleido (TC-04: charts are WRAPPER-rendered, never an
in-graph tool_call). Adds Q2 exact-timestamp annotations and Q4 misleading-chart suppression.

Also exposes ``render_chart(spec, path)`` so this same module can serve as the harness
``chart.render`` helper ($GOATCS_CHART_HELPER) — one rendering core, no duplication.
"""
from __future__ import annotations

import os
from pathlib import Path

# Price-dependent chart types that must be SKIPPED when quotes are offline/stale (Q4).
_PRICE_DEPENDENT = {"portfolio_breakdown", "portfolio", "compound_growth_live"}


def _render(spec: dict, out_path: str) -> None:
    import plotly.graph_objects as go  # lazy
    ctype = str(spec.get("type", "bar")).lower()
    labels = list(spec.get("labels") or spec.get("x") or [])
    values = list(spec.get("values") or spec.get("y") or [])
    fig = go.Figure()
    if ctype == "pie":
        fig.add_trace(go.Pie(labels=labels, values=values))
    elif ctype in ("line", "scatter"):
        mode = "lines+markers" if ctype == "line" else "markers"
        series = spec.get("series")
        if series:
            for s in series:
                fig.add_trace(go.Scatter(x=list(s.get("x", [])), y=list(s.get("y", [])),
                                         mode=mode, name=str(s.get("name", ""))))
        else:
            fig.add_trace(go.Scatter(x=labels, y=values, mode=mode))
    else:
        fig.add_trace(go.Bar(x=labels, y=values))
    fig.update_layout(title=str(spec.get("title", "")),
                      xaxis_title=str(spec.get("xlabel", "")),
                      yaxis_title=str(spec.get("ylabel", "")),
                      template="plotly_white")
    fig.write_image(str(out_path), format=(os.path.splitext(str(out_path))[1].lstrip(".") or "png"))


def render_chart(spec: dict, path: Path) -> dict:
    """Harness chart.render helper API. Never raises."""
    try:
        _render(spec, str(path))
        return {"status": "ok", "image_path": str(path), "format": "png"}
    except Exception as ex:
        return {"status": "error", "image_path": "", "format": "png",
                "generation_note": f"render fault: {type(ex).__name__}"}


def _is_misleading(spec: dict, quote_data: dict | None) -> str | None:
    """Return a skip-reason if this price-dependent chart would mislead (Q4), else None."""
    explicit = spec.get("skip")
    if explicit:
        return spec.get("skip_reason") or "marked skip by chart spec"
    ctype = str(spec.get("type", "")).lower()
    title = str(spec.get("title", "")).lower()
    price_dep = ctype in _PRICE_DEPENDENT or "portfolio" in title
    if price_dep and quote_data and quote_data.get("offline_flag"):
        return "prices are OFFLINE/cached — omitted to avoid showing misleading values"
    if price_dep and quote_data:
        if any(p.get("stale") for p in (quote_data.get("prices") or {}).values()):
            return "prices are STALE (>24h) — omitted to avoid showing misleading values"
    return None


def _timestamp_suffix(quote_data: dict | None) -> str:
    if not quote_data:
        return ""
    return f" [as of {quote_data.get('quote_fetch_ts')}]"


def render_specs(chart_specs, out_dir: str, quote_data: dict | None = None) -> dict:
    """Render a list of chart specs. Returns {rendered:[{title,path}], skipped:[{title,reason}]}.

    Q2: price-dependent chart titles get the exact quote timestamp appended.
    Q4: misleading price-dependent charts are skipped with a recorded reason.
    """
    os.makedirs(out_dir, exist_ok=True)
    rendered, skipped = [], []
    for i, spec in enumerate(chart_specs or []):
        title = str(spec.get("title", f"chart_{i}"))
        reason = _is_misleading(spec, quote_data)
        if reason:
            skipped.append({"title": title, "reason": reason})
            continue
        spec = dict(spec)
        ctype = str(spec.get("type", "")).lower()
        if ctype in _PRICE_DEPENDENT or "portfolio" in title.lower() or "growth" in title.lower():
            spec["title"] = title + _timestamp_suffix(quote_data)
        path = spec.get("path") or os.path.join(out_dir, f"chart_{i}.png")
        res = render_chart(spec, Path(path))
        if res["status"] == "ok":
            rendered.append({"title": spec.get("title", title), "path": res["image_path"]})
        else:
            skipped.append({"title": title, "reason": res.get("generation_note", "render error")})
    return {"rendered": rendered, "skipped": skipped}

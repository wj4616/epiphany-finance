"""Assemble the final chart-embedded PDF (build-plan decision #6: PDF is wrapper-owned so charts —
rendered post-graph — actually make it in). Reuses the verified-research-report-lg ``finalize_pdf``
helper (resolved like the harness pdf.render: $GOATCS_PDF_HELPER > built-in default) and degrades
to a minimal WeasyPrint render, then to an error dict — never raises (INV-5).
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_DEFAULT_PDF_HELPER = "~/.claude/skills/verified-research-report-lg/helpers/pdf_postprocess.py"


def _resolve_helper() -> str:
    return os.path.expanduser(os.environ.get("GOATCS_PDF_HELPER") or _DEFAULT_PDF_HELPER)


def inject_charts(markdown: str, render_result: dict) -> str:
    """Append rendered charts as file:// images, and note any skipped charts (Q4)."""
    parts = [markdown]
    rendered = (render_result or {}).get("rendered") or []
    skipped = (render_result or {}).get("skipped") or []
    if rendered:
        parts.append("\n\n## Charts\n")
        for ch in rendered:
            uri = Path(ch["path"]).resolve().as_uri()
            parts.append(f"\n![{ch['title']}]({uri})\n")
    for sk in skipped:
        parts.append(f"\n> _Chart omitted — {sk['title']}: {sk['reason']}._\n")
    return "".join(parts)


def _minimal_pdf(markdown: str, out_path: str) -> dict:
    """Fallback: very plain HTML -> PDF via WeasyPrint, so a PDF still ships if the helper is absent."""
    try:
        from weasyprint import HTML
        html = "<html><body>" + "".join(
            f"<p>{line}</p>" for line in markdown.splitlines()) + "</body></html>"
        HTML(string=html).write_pdf(out_path)
        return {"status": "ok", "pdf_path": out_path, "page_count": 0,
                "generation_note": "minimal fallback renderer (helper unavailable)"}
    except Exception as ex:
        return {"status": "error", "pdf_path": "", "page_count": 0,
                "generation_note": f"pdf unavailable: {type(ex).__name__}"}


def build_report_pdf(markdown: str, out_path: str, *, render_result: dict | None = None,
                     document_type: str = "Financial Analysis Report",
                     title: str | None = "Personal Financial Report") -> dict:
    """Inject charts, then render the PDF. Returns {status, pdf_path, page_count, generation_note}."""
    full_md = inject_charts(markdown, render_result or {})
    helper = _resolve_helper()
    if not os.path.exists(helper):
        return _minimal_pdf(full_md, out_path)
    try:
        spec = importlib.util.spec_from_file_location("efin_pdf_helper", helper)
        mod = importlib.util.module_from_spec(spec)   # type: ignore[arg-type]
        spec.loader.exec_module(mod)                  # type: ignore[union-attr]
        try:
            result = mod.finalize_pdf(full_md, Path(out_path), "STANDARD", document_type, title=title)
        except TypeError:                             # older helper signature without title=
            result = mod.finalize_pdf(full_md, Path(out_path), "STANDARD", document_type)
        return {"status": result.get("status", "ok"),
                "pdf_path": result.get("pdf_path") or out_path,
                "page_count": int(result.get("page_count") or 0),
                "generation_note": f"helper={helper}"}
    except Exception:
        return _minimal_pdf(full_md, out_path)

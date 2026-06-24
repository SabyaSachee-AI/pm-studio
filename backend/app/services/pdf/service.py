"""PDF generation via WeasyPrint."""

from __future__ import annotations

from html import escape


def render_html_to_pdf(html_content: str) -> bytes:
    """Convert HTML string to PDF bytes."""
    try:
        from weasyprint import HTML
    except OSError as exc:
        raise RuntimeError(
            "WeasyPrint system libraries are not installed. "
            "Use Docker backend image or install GTK/Pango dependencies."
        ) from exc
    return HTML(string=html_content).write_pdf()


def _formal_a4_css() -> str:
    """Shared A4 portrait print styles (matches frontend FORMAL_PRINT_STYLES)."""
    return """
        @page { size: A4 portrait; margin: 2cm 2cm 2.5cm 2cm; }
        body { font-family: Georgia, serif; color: #111; font-size: 11pt; line-height: 1.5; }
        h1 { font-size: 16pt; text-align: center; margin-bottom: 4pt; }
        h2 { font-size: 11pt; margin-top: 14pt; margin-bottom: 6pt; page-break-after: avoid; }
        .subtitle { text-align: center; font-size: 9pt; color: #666; text-transform: uppercase; }
        .meta-table { width: 100%; border-collapse: collapse; margin: 18pt 0; font-size: 10pt; }
        .meta-table td { padding: 4pt 8pt 4pt 0; vertical-align: top; }
        .meta-table td:first-child { font-weight: bold; width: 28%; }
        p, li { font-size: 10pt; line-height: 1.5; }
        .section { page-break-inside: avoid; margin-top: 12pt; }
        table.data { width: 100%; border-collapse: collapse; margin-top: 8pt; font-size: 9pt; }
        table.data th, table.data td { border: 1px solid #ccc; padding: 6pt; text-align: left; }
        table.data th { background: #f5f5f5; }
        hr { border: none; border-top: 1px solid #999; margin: 16pt 0; }
        footer { font-size: 9pt; margin-top: 16pt; }
    """


def _e(value: object) -> str:
    return escape("" if value is None else str(value))


def _strip_meta(content: dict) -> dict:
    return {k: v for k, v in content.items() if k != "_meta"}


def build_clarification_html(
    project_name: str,
    filename: str,
    gaps: list[dict],
    questions: list[str],
) -> str:
    """Build HTML for a clarification questions PDF."""
    gap_rows = "".join(
        f"<tr><td>{gap.get('category', '').upper()}</td>"
        f"<td>{gap.get('description', '')}</td>"
        f"<td>{gap.get('question') or '—'}</td></tr>"
        for gap in gaps
    )
    question_items = "".join(f"<li>{q}</li>" for q in questions)
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; color: #111; }}
        h1 {{ font-size: 22px; margin-bottom: 4px; }}
        h2 {{ font-size: 16px; margin-top: 28px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; font-size: 12px; }}
        th {{ background: #f5f5f5; }}
        ul {{ margin-top: 8px; }}
        .meta {{ color: #555; font-size: 12px; }}
      </style>
    </head>
    <body>
      <h1>Clarification questions</h1>
      <p class="meta">Project: {project_name} · Source: {filename}</p>
      <h2>Requirement gaps</h2>
      <table>
        <thead><tr><th>Category</th><th>Gap</th><th>Question</th></tr></thead>
        <tbody>{gap_rows}</tbody>
      </table>
      <h2>Technical questions</h2>
      <ul>{question_items}</ul>
    </body>
    </html>
    """


def build_prd_html(prd: dict, project_name: str, version: int) -> str:
    """Build printable HTML for a PRD document."""
    body = _strip_meta(prd)
    features = "".join(
        f"<li><strong>{_e(f.get('title'))}</strong> [{_e(f.get('priority'))}] — "
        f"{_e(f.get('description'))}</li>"
        for f in body.get("features", [])
    )
    stories = "".join(
        f"<li>As a {_e(s.get('as_a'))}, I want to {_e(s.get('i_want_to'))}, "
        f"so that {_e(s.get('so_that'))}</li>"
        for s in body.get("user_stories", [])
    )
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <style>{_formal_a4_css()}</style>
    </head>
    <body>
      <h1>Product requirements document</h1>
      <p class="subtitle">{_e(project_name)} · Version {version}</p>
      <div class="section">
        <h2>Executive summary</h2>
        <p>{_e(body.get('executive_summary', ''))}</p>
      </div>
      <div class="section">
        <h2>Problem statement</h2>
        <p>{_e(body.get('problem_statement', ''))}</p>
      </div>
      <div class="section">
        <h2>Features</h2>
        <ul>{features}</ul>
      </div>
      <div class="section">
        <h2>User stories</h2>
        <ul>{stories}</ul>
      </div>
    </body>
    </html>
    """


def build_srs_html(srs: dict, project_name: str, version: int) -> str:
    """Build printable HTML for an SRS document (A4 portrait, IEEE-style sections)."""
    body = _strip_meta(srs)
    intro = body.get("introduction")
    if isinstance(intro, dict):
        intro_purpose = intro.get("purpose", "")
        intro_scope = intro.get("scope", body.get("scope", ""))
        definitions = intro.get("definitions", body.get("definitions", []))
    else:
        intro_purpose = intro or ""
        intro_scope = body.get("scope", "")
        definitions = body.get("definitions", [])

    overall = body.get("overall_description") or {}
    frs = body.get("functional_requirements") or []
    nfrs = body.get("non_functional_requirements") or body.get("nonfunctional_requirements") or []

    fr_blocks = ""
    for i, fr in enumerate(frs):
        fr_id = fr.get("id") or fr.get("fr_number") or f"FR-{i + 1}"
        criteria = "".join(f"<li>✓ {_e(c)}</li>" for c in (fr.get("test_criteria") or []))
        fr_blocks += f"""
        <div class="section">
          <p><strong>{_e(fr_id)}: {_e(fr.get('title'))}</strong> [{_e(fr.get('priority', '')).upper()}]</p>
          <p>{_e(fr.get('description'))}</p>
          {f"<p>Input: {_e(fr.get('inputs'))}</p>" if fr.get('inputs') else ""}
          {f"<p>Processing: {_e(fr.get('processing'))}</p>" if fr.get('processing') else ""}
          {f"<p>Output: {_e(fr.get('outputs'))}</p>" if fr.get('outputs') else ""}
          {f"<ul>{criteria}</ul>" if criteria else ""}
        </div>
        """

    nfr_blocks = ""
    for nfr in nfrs:
        nfr_blocks += f"""
        <p><strong>[{_e(nfr.get('category', 'Other'))}]</strong> {_e(nfr.get('description'))}<br/>
        Metric: {_e(nfr.get('metric', '—'))} | Threshold: {_e(nfr.get('threshold', '—'))}</p>
        """

    definition_items = "".join(f"<li>{_e(d)}</li>" for d in definitions)
    function_items = "".join(
        f"<li>{_e(f)}</li>" for f in (overall.get("product_functions") or [])
    )
    user_items = "".join(
        f"<li>{_e(u)}</li>" for u in (overall.get("user_characteristics") or [])
    )
    security_items = "".join(
        f"<li>{_e(s)}</li>" for s in (body.get("security_requirements") or [])
    )
    constraint_items = "".join(f"<li>{_e(c)}</li>" for c in (body.get("constraints") or []))

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <style>{_formal_a4_css()}</style>
    </head>
    <body>
      <h1>Software requirements specification</h1>
      <p class="subtitle">IEEE 830 compliant · {_e(project_name)} · Version {version}</p>
      <table class="meta-table">
        <tr><td>Project</td><td>{_e(project_name)}</td></tr>
        <tr><td>Version</td><td>v{version}</td></tr>
      </table>
      <hr/>
      <div class="section">
        <h2>1. Introduction</h2>
        <p><strong>Purpose:</strong> {_e(intro_purpose)}</p>
        <p><strong>Scope:</strong> {_e(intro_scope)}</p>
        <ul>{definition_items}</ul>
      </div>
      <div class="section">
        <h2>2. Overall description</h2>
        <p>{_e(overall.get('product_perspective', ''))}</p>
        <ul>{function_items}{user_items}</ul>
      </div>
      <div class="section">
        <h2>3. Functional requirements</h2>
        {fr_blocks}
      </div>
      <div class="section">
        <h2>4. Non-functional requirements</h2>
        {nfr_blocks}
      </div>
      <div class="section">
        <h2>7. Security requirements</h2>
        <ul>{security_items}</ul>
      </div>
      <div class="section">
        <h2>8. Constraints</h2>
        <ul>{constraint_items}</ul>
      </div>
      <footer>
        <p>Confirmed signature: _________________________</p>
      </footer>
    </body>
    </html>
    """

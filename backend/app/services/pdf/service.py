"""PDF generation via WeasyPrint."""

from __future__ import annotations


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
    features = "".join(
        f"<li><strong>{f.get('title')}</strong> [{f.get('priority')}] — "
        f"{f.get('description')}</li>"
        for f in prd.get("features", [])
    )
    stories = "".join(
        f"<li>As a {s.get('as_a')}, I want to {s.get('i_want_to')}, "
        f"so that {s.get('so_that')}</li>"
        for s in prd.get("user_stories", [])
    )
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <style>
        body {{ font-family: Georgia, serif; margin: 40px; color: #111; }}
        h1 {{ font-size: 24px; }}
        h2 {{ font-size: 16px; margin-top: 24px; border-bottom: 1px solid #ddd; }}
        p, li {{ font-size: 13px; line-height: 1.5; }}
        .header {{ margin-bottom: 24px; }}
        .meta {{ color: #666; font-size: 12px; }}
      </style>
    </head>
    <body>
      <div class="header">
        <h1>Product requirements document</h1>
        <p class="meta">{project_name} · Version {version}</p>
      </div>
      <h2>Executive summary</h2>
      <p>{prd.get("executive_summary", "")}</p>
      <h2>Problem statement</h2>
      <p>{prd.get("problem_statement", "")}</p>
      <h2>Features</h2>
      <ul>{features}</ul>
      <h2>User stories</h2>
      <ul>{stories}</ul>
    </body>
    </html>
    """


def build_srs_html(srs: dict, project_name: str, version: int) -> str:
    """Build printable HTML for an SRS document."""
    fr_rows = "".join(
        f"<tr><td>{fr.get('fr_number', '')}</td>"
        f"<td>{fr.get('title', '')}</td>"
        f"<td>{fr.get('description', '')}</td>"
        f"<td>{fr.get('priority', '')}</td></tr>"
        for fr in srs.get("functional_requirements", [])
    )
    nfr_items = "".join(
        f"<li><strong>{nfr.get('category', '')}</strong>: {nfr.get('description', '')} "
        f"({nfr.get('metric', '')}: {nfr.get('threshold', '')})</li>"
        for nfr in srs.get("nonfunctional_requirements", [])
    )
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <style>
        body {{ font-family: Georgia, serif; margin: 40px; color: #111; }}
        h1 {{ font-size: 24px; }}
        h2 {{ font-size: 16px; margin-top: 24px; border-bottom: 1px solid #ddd; }}
        p, li {{ font-size: 13px; line-height: 1.5; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; font-size: 12px; }}
        th {{ background: #f5f5f5; }}
        .meta {{ color: #666; font-size: 12px; }}
      </style>
    </head>
    <body>
      <h1>Software requirements specification</h1>
      <p class="meta">{project_name} · Version {version}</p>
      <h2>Introduction</h2>
      <p>{srs.get("introduction", "")}</p>
      <h2>Scope</h2>
      <p>{srs.get("scope", "")}</p>
      <h2>Functional requirements</h2>
      <table>
        <thead><tr><th>ID</th><th>Title</th><th>Description</th><th>Priority</th></tr></thead>
        <tbody>{fr_rows}</tbody>
      </table>
      <h2>Non-functional requirements</h2>
      <ul>{nfr_items}</ul>
    </body>
    </html>
    """

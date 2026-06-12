"""Sanitize AI-generated Mermaid diagrams for Mermaid v11 (mirrors frontend/lib/mermaidSanitize.ts)."""

from __future__ import annotations

import re
from typing import Any


def _expand_single_line_er(chart: str) -> str:
    if "\n" in chart:
        return chart
    if not chart.lower().startswith("erdiagram"):
        return chart
    out = re.sub(r"^erDiagram\s*", "erDiagram\n", chart, flags=re.I)
    out = re.sub(
        r"(\s+:\s*[\w_]+)\s+(?=[A-Z_][A-Z0-9_]*\s+(?:\|\||}o|o\{|\.\.))",
        r"\1\n",
        out,
    )
    return out


def _fix_sequence(chart: str) -> str:
    if not re.match(r"^sequenceDiagram", chart, re.I | re.M):
        return chart
    lines: list[str] = []
    for line in chart.split("\n"):
        m = re.match(r"^(\s*participant\s+\S+\s+as\s+)(.+)$", line, re.I)
        if m:
            alias = m.group(2).strip()
            if not alias.startswith('"'):
                line = f'{m.group(1)}"{alias.replace(chr(34), chr(39))}"'
        lines.append(line)
    return "\n".join(lines)


def _fix_er(chart: str) -> str:
    if not re.match(r"^erDiagram", chart, re.I | re.M):
        return chart
    lines: list[str] = []
    for line in chart.split("\n"):
        trimmed = line.strip()
        if not trimmed or trimmed.lower() == "erdiagram":
            lines.append(line)
            continue
        if re.search(r"(\|\||--|\.\.|}o|o\{)", trimmed):

            def upper_right(m: re.Match[str]) -> str:
                return (
                    f"{m.group(1)}{m.group(2).upper()}{m.group(3)}{m.group(4)}"
                    f"{m.group(5).upper()}{m.group(6) or ''}"
                )

            line = re.sub(
                r"^(\s*)([A-Z0-9_]+)(\s+(?:\|\||}o|o\{|\.\.)[\s\S]+?)(\s+)([a-z][a-z0-9_]*)(\s*(:.*))?$",
                upper_right,
                line,
                flags=re.I,
            )
        lines.append(line)
    return "\n".join(lines)


def _slug_subgraph_id(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_")[:40]
    return f"sg_{slug}" if slug else "sg_group"


def _fix_flowchart(chart: str) -> str:
    if not re.match(r"^flowchart", chart, re.I | re.M):
        return chart

    # subgraph id["Title"] → subgraph id ["Title"]
    chart = re.sub(r"^(\s*subgraph\s+)(\w+)\[", r"\1\2 [", chart, flags=re.M)

    def quoted_subgraph(m: re.Match[str]) -> str:
        title = m.group(2).replace('"', "'")
        return f'{m.group(1)}subgraph {_slug_subgraph_id(title)} ["{title}"]'

    chart = re.sub(r'^(\s*)subgraph\s+"([^"]+)"\s*$', quoted_subgraph, chart, flags=re.M)

    chart = re.sub(
        r'\b(\w+)\["([^"]+)"\s*:\s*(\d+)\s*\]',
        lambda m: f'{m.group(1)}["{m.group(2).replace(chr(34), chr(39))} :{m.group(3)}"]',
        chart,
    )
    chart = re.sub(
        r'\b(\w+)\[\("([^"]+)"\)\s*:\s*(\d+)\s*\]',
        lambda m: f'{m.group(1)}[("{m.group(2).replace(chr(34), chr(39))} :{m.group(3)}")]',
        chart,
    )
    chart = re.sub(
        r'\b(\w+)\[\(([^")]+)\)\s*:\s*(\d+)\s*\]',
        lambda m: f'{m.group(1)}[("{m.group(2).strip().replace(chr(34), chr(39))} :{m.group(3)}")]',
        chart,
    )
    chart = re.sub(
        r"\b(\w+)\[([^\]\"{}|()]+[/:<>&@()][^\]\"{}|()]*)\]",
        lambda m: f'{m.group(1)}["{m.group(2).replace(chr(34), chr(39))}"]',
        chart,
    )
    chart = re.sub(
        r'\b(\w+)\[\("([^"]+)"\)\]',
        lambda m: f'{m.group(1)}[("{m.group(2).replace(chr(34), chr(39))}")]',
        chart,
    )
    return chart


def sanitize_mermaid(raw: str) -> str:
    if not raw or not str(raw).strip():
        return ""

    chart = str(raw).strip()
    chart = re.sub(r"^```mermaid\s*", "", chart, flags=re.I)
    chart = re.sub(r"^```\s*", "", chart)
    chart = re.sub(r"\s*```\s*$", "", chart)
    chart = chart.strip()

    chart = re.sub(r"%%\{[\s\S]*?\}%%\s*", "", chart)
    chart = re.sub(r"<!--[\s\S]*?-->", "", chart)
    chart = chart.replace("\r\n", "\n").replace("\r", "\n")
    chart = "\n".join(line.rstrip() for line in chart.split("\n"))

    for pattern in (
        r"^\s*classDef\s+.*$",
        r"^\s*class\s+[\w,\s]+\s+\w+\s*$",
        r"^\s*style\s+\w+.*$",
        r"^\s*linkStyle\s+.*$",
        r"^\s*%%(?!\{).*$",
    ):
        chart = re.sub(pattern, "", chart, flags=re.M)

    chart = re.sub(r"^graph\s*$", "flowchart TD", chart, flags=re.M)
    chart = re.sub(r"^graph\s+(LR|TD|RL|BT|TB)\b", r"flowchart \1", chart, flags=re.M)
    chart = re.sub(r"^graph\s+TB\b", "flowchart TD", chart, flags=re.M)

    chart = _expand_single_line_er(chart)
    chart = _fix_sequence(chart)
    chart = _fix_er(chart)
    chart = _fix_flowchart(chart)

    chart = re.sub(
        r"^(\s*)([\w ]+?)\s*->\s*([\w ]+?)\s*:",
        r"\1\2->>\3:",
        chart,
        flags=re.M,
    )
    chart = re.sub(r"(\w)\s+->>\s*(\w)", r"\1->>\2", chart)
    chart = re.sub(r"(\w)\s+-->\s*(\w)", r"\1-->\2", chart)

    opens = len(re.findall(r"^\s*subgraph\b", chart, re.M))
    closes = len(re.findall(r"^\s*end\b", chart, re.M))
    if opens > closes:
        chart += "\n" + "end\n" * (opens - closes)

    chart = re.sub(r"\n{3,}", "\n\n", chart)
    return chart.strip()


def sanitize_doc_diagrams(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return doc
    diagrams = doc.get("diagrams")
    if not isinstance(diagrams, dict):
        return doc
    doc = dict(doc)
    doc["diagrams"] = {
        k: sanitize_mermaid(str(v)) if v else ""
        for k, v in diagrams.items()
    }
    return doc


def sanitize_all_docs(docs: dict[str, dict[str, Any] | None]) -> dict[str, dict[str, Any] | None]:
    return {k: sanitize_doc_diagrams(v) if v else None for k, v in docs.items()}

"""Sanitize Mermaid diagram source for reliable rendering."""

from __future__ import annotations

import re


def sanitize_mermaid(chart: str) -> str:
    if not chart or not chart.strip():
        return ""
    text = chart.strip()
    # subgraph ID["Title"] -> subgraph ID ["Title"] (Mermaid v11)
    text = re.sub(
        r"subgraph\s+(\w+)\[([^\]]+)\]",
        r"subgraph \1 [\2]",
        text,
    )
    # Remove port suffixes inside node labels: ["API :8000"] -> ["API"]
    text = re.sub(r'(\[[^\]"]*?)\s*:\d+([^\]"]*?\])', r"\1\2", text)
    text = re.sub(r'(\("[^)"]*?)\s*:\d+([^)"]*?\))', r"\1\2", text)
    return text

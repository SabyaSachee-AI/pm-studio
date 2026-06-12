/** Sanitize Mermaid diagram source for reliable rendering (mirrors backend mermaid_sanitize.py). */

function expandSingleLineEr(chart: string): string {
  if (chart.includes("\n")) return chart;
  if (!chart.toLowerCase().startsWith("erdiagram")) return chart;
  let out = chart.replace(/^erDiagram\s*/i, "erDiagram\n");
  out = out.replace(
    /(\s+:\s*[\w_]+)\s+(?=[A-Z_][A-Z0-9_]*\s+(?:\|\||}o|o\{|\.\.))/g,
    "$1\n",
  );
  return out;
}

function fixSequence(chart: string): string {
  if (!/^sequenceDiagram/im.test(chart)) return chart;
  return chart
    .split("\n")
    .map((line) => {
      const m = line.match(/^(\s*participant\s+\S+\s+as\s+)(.+)$/i);
      if (!m) return line;
      const alias = m[2].trim();
      if (!alias.startsWith('"')) {
        return `${m[1]}"${alias.replace(/"/g, "'")}"`;
      }
      return line;
    })
    .join("\n");
}

function slugSubgraphId(title: string): string {
  const slug = title.replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40);
  return slug ? `sg_${slug}` : "sg_group";
}

function fixFlowchart(chart: string): string {
  if (!/^flowchart/im.test(chart)) return chart;

  let text = chart.replace(/^(\s*subgraph\s+)(\w+)\[/gm, "$1$2 [");

  text = text.replace(/^(\s*)subgraph\s+"([^"]+)"\s*$/gm, (_m, indent: string, title: string) => {
    const safe = title.replace(/"/g, "'");
    return `${indent}subgraph ${slugSubgraphId(title)} ["${safe}"]`;
  });

  // Port suffix outside brackets: API["Label"] :8000 → API["Label :8000"]
  text = text.replace(
    /\b(\w+)\["([^"]+)"\s*:\s*(\d+)\s*\]/g,
    (_m, id: string, label: string, port: string) =>
      `${id}["${label.replace(/"/g, "'")} :${port}"]`,
  );
  text = text.replace(
    /\b(\w+)\[\("([^"]+)"\)\s*:\s*(\d+)\s*\]/g,
    (_m, id: string, label: string, port: string) =>
      `${id}[("${label.replace(/"/g, "'")} :${port}")]`,
  );
  text = text.replace(
    /\b(\w+)\[\(([^")]+)\)\s*:\s*(\d+)\s*\]/g,
    (_m, id: string, label: string, port: string) =>
      `${id}[("${label.trim().replace(/"/g, "'")} :${port}")]`,
  );

  // Quote labels with special characters (ports, slashes, etc.)
  text = text.replace(
    /\b(\w+)\[([^\]"{}|()]+[/:<>&@()][^\]"{}|()]*)\]/g,
    (_m, id: string, label: string) => `${id}["${label.replace(/"/g, "'")}"]`,
  );

  text = text.replace(
    /\b(\w+)\[\("([^"]+)"\)\]/g,
    (_m, id: string, label: string) => `${id}[("${label.replace(/"/g, "'")}")]`,
  );

  return text;
}

/** Ensure arrows have spaces between node ids: API-->DB → API --> DB */
function fixArrowSpacing(chart: string): string {
  return chart
    .replace(/(\w)-->>(\w)/g, "$1 -->> $2")
    .replace(/(\w)-->(\w)/g, "$1 --> $2");
}

export function sanitizeMermaid(chart: string): string {
  if (!chart?.trim()) return "";

  let text = chart.trim();
  text = text.replace(/^```mermaid\s*/i, "");
  text = text.replace(/^```\s*/, "");
  text = text.replace(/\s*```\s*$/, "");
  text = text.trim();

  text = text.replace(/%%\{[\s\S]*?\}%%\s*/g, "");
  text = text.replace(/<!--[\s\S]*?-->/g, "");
  text = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  text = text.split("\n").map((l) => l.trimEnd()).join("\n");

  for (const pattern of [
    /^\s*classDef\s+.*$/gm,
    /^\s*class\s+[\w,\s]+\s+\w+\s*$/gm,
    /^\s*style\s+\w+.*$/gm,
    /^\s*linkStyle\s+.*$/gm,
    /^\s*%%(?!\{).*$/gm,
  ]) {
    text = text.replace(pattern, "");
  }

  text = text.replace(/^graph\s*$/gm, "flowchart TD");
  text = text.replace(/^graph\s+(LR|TD|RL|BT|TB)\b/gim, "flowchart $1");
  text = text.replace(/^graph\s+TB\b/gim, "flowchart TD");

  text = expandSingleLineEr(text);
  text = fixSequence(text);
  text = fixFlowchart(text);
  text = fixArrowSpacing(text);

  const opens = (text.match(/^\s*subgraph\b/gim) ?? []).length;
  const closes = (text.match(/^\s*end\b/gim) ?? []).length;
  if (opens > closes) {
    text += `\n${"end\n".repeat(opens - closes)}`;
  }

  text = text.replace(/\n{3,}/g, "\n\n");
  return text.trim();
}

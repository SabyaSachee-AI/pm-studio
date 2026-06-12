/** Sanitize Mermaid diagram source for reliable rendering. */

export function sanitizeMermaid(chart: string): string {
  if (!chart?.trim()) return "";
  let text = chart.trim();
  text = text.replace(/subgraph\s+(\w+)\[([^\]]+)\]/g, "subgraph $1 [$2]");
  text = text.replace(/(\[[^\]"]*?)\s*:\d+([^\]"]*?\])/g, "$1$2");
  text = text.replace(/(\("[^)"]*?)\s*:\d+([^)"]*?\))/g, "$1$2");
  return text;
}

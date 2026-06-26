"use client";

import Editor from "@monaco-editor/react";

/** Map a file path/extension to a Monaco language id. */
function languageForPath(path: string): string {
  const lower = path.toLowerCase();
  if (lower.endsWith("dockerfile") || lower.includes("dockerfile")) return "dockerfile";
  const ext = lower.split(".").pop() ?? "";
  const map: Record<string, string> = {
    ts: "typescript", tsx: "typescript",
    js: "javascript", jsx: "javascript", mjs: "javascript", cjs: "javascript",
    py: "python",
    json: "json",
    md: "markdown", mdx: "markdown",
    css: "css", scss: "scss",
    html: "html",
    yml: "yaml", yaml: "yaml",
    sh: "shell", bash: "shell",
    sql: "sql",
    toml: "ini", ini: "ini", env: "ini",
    xml: "xml",
    go: "go", rs: "rust", java: "java", rb: "ruby", php: "php",
  };
  return map[ext] ?? "plaintext";
}

export type CodeEditorProps = {
  value: string;
  path: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
};

/** Monaco code editor: syntax highlighting, auto-indent, bracket pair colorization. */
export function CodeEditor({ value, path, onChange, readOnly = false }: CodeEditorProps) {
  return (
    <Editor
      language={languageForPath(path)}
      value={value}
      onChange={(v) => onChange(v ?? "")}
      theme="vs-dark"
      loading={<div className="p-3 text-xs text-gray-600">Loading editor…</div>}
      options={{
        readOnly,
        fontSize: 12,
        lineHeight: 18,
        tabSize: 2,
        minimap: { enabled: true, scale: 1 },
        scrollBeyondLastLine: false,
        automaticLayout: true,
        wordWrap: "off",
        smoothScrolling: true,
        bracketPairColorization: { enabled: true },
        guides: { bracketPairs: true, indentation: true },
        renderLineHighlight: "all",
        fontLigatures: true,
        scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 },
      }}
    />
  );
}

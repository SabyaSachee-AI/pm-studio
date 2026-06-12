declare module "jspdf-autotable" {
  import type { jsPDF } from "jspdf";

  interface CellHookData {
    section: "head" | "body" | "foot";
    column: { index: number };
    cell: {
      text: string[];
      styles: Record<string, unknown>;
    };
  }

  interface AutoTableOptions {
    startY?: number;
    margin?: { top?: number; right?: number; bottom?: number; left?: number };
    head?: string[][];
    body?: string[][];
    styles?: Record<string, unknown>;
    headStyles?: Record<string, unknown>;
    alternateRowStyles?: Record<string, unknown>;
    columnStyles?: Record<number, Record<string, unknown>>;
    theme?: string;
    didParseCell?: (data: CellHookData) => void;
  }

  export default function autoTable(doc: jsPDF, options: AutoTableOptions): void;
}

import html2canvas from "html2canvas";

export interface SvgPngImage {
  dataUrl: string;
  widthPx: number;
  heightPx: number;
  aspectRatio: number;
}

/** Prepare SVG for rasterization — keep labels (foreignObject/text); fix dimensions only. */
function prepareSvgForRaster(svg: string): { markup: string; width: number; height: number } {
  const parser = new DOMParser();
  const doc = parser.parseFromString(svg, "image/svg+xml");
  const el = doc.documentElement;

  if (!el.getAttribute("xmlns")) {
    el.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  }

  const viewBox = el.getAttribute("viewBox")?.trim().split(/\s+/).map(Number);
  let width = 900;
  let height = 600;
  if (viewBox && viewBox.length === 4) {
    width = viewBox[2];
    height = viewBox[3];
    el.setAttribute("width", String(width));
    el.setAttribute("height", String(height));
  }

  el.removeAttribute("style");

  const markup = new XMLSerializer().serializeToString(el);
  return { markup, width, height };
}


export async function rasterizeSvgForPdf(
  svg: string,
  scale = 2,
): Promise<SvgPngImage | null> {
  if (!svg.trim()) return null;

  const { markup, width, height } = prepareSvgForRaster(svg);

  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-same-origin");
  iframe.style.cssText =
    "position:fixed;left:-10000px;top:0;width:1px;height:1px;border:0;opacity:0;pointer-events:none;";
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument;
  if (!doc) {
    iframe.remove();
    return null;
  }

  doc.open();
  doc.write(
    '<!DOCTYPE html><html><head><meta charset="utf-8">' +
      "<style>html,body{margin:0;padding:12px;background:#ffffff;}</style>" +
      "</head><body></body></html>",
  );
  doc.close();

  const host = doc.createElement("div");
  host.style.cssText = `display:inline-block;background:#ffffff;width:${width}px;`;
  host.innerHTML = markup;
  doc.body.appendChild(host);

  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  });

  try {
    const canvas = await html2canvas(host, {
      backgroundColor: "#ffffff",
      scale,
      logging: false,
      useCORS: true,
      width: Math.ceil(width + 24),
      height: Math.ceil(height + 24),
    });

    if (!canvas.width || !canvas.height) return null;

    return {
      dataUrl: canvas.toDataURL("image/png"),
      widthPx: canvas.width,
      heightPx: canvas.height,
      aspectRatio: canvas.width / canvas.height,
    };
  } catch {
    return null;
  } finally {
    iframe.remove();
  }
}

/** @deprecated Use rasterizeSvgForPdf — Image() cannot render foreignObject labels. */
export async function svgStringToPngDataUrl(
  svg: string,
  scale = 2,
): Promise<SvgPngImage | null> {
  return rasterizeSvgForPdf(svg, scale);
}

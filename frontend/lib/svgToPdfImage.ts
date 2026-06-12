export interface SvgPngImage {
  dataUrl: string;
  widthPx: number;
  heightPx: number;
  aspectRatio: number;
}

function parseSvgDimensions(svg: string): { width: number; height: number } {
  const parser = new DOMParser();
  const doc = parser.parseFromString(svg, "image/svg+xml");
  const el = doc.documentElement;
  const viewBox = el.getAttribute("viewBox")?.trim().split(/\s+/).map(Number);
  let width = parseFloat(el.getAttribute("width")?.replace(/px$/, "") ?? "0");
  let height = parseFloat(el.getAttribute("height")?.replace(/px$/, "") ?? "0");

  if (viewBox && viewBox.length === 4) {
    if (!width) width = viewBox[2];
    if (!height) height = viewBox[3];
  }

  if (!width || !height || !Number.isFinite(width) || !Number.isFinite(height)) {
    return { width: 900, height: 600 };
  }
  return { width, height };
}

function prepareSvgForRaster(svg: string): string {
  let prepared = svg.trim();
  if (!prepared.includes('xmlns="http://www.w3.org/2000/svg"')) {
    prepared = prepared.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
  }
  if (!prepared.includes("<rect") || !prepared.includes('fill="#ffffff"')) {
    prepared = prepared.replace(
      /<svg([^>]*)>/,
      '<svg$1><rect width="100%" height="100%" fill="#ffffff"/>',
    );
  }
  return prepared;
}

/** Rasterize an SVG string to a crisp PNG data URL for PDF embedding. */
export async function svgStringToPngDataUrl(
  svg: string,
  scale = 2.5,
): Promise<SvgPngImage | null> {
  if (!svg.trim()) return null;

  const { width, height } = parseSvgDimensions(svg);
  const prepared = prepareSvgForRaster(svg);
  const blob = new Blob([prepared], { type: "image/svg+xml;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);

  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("SVG rasterization failed"));
      image.src = objectUrl;
    });

    const canvas = document.createElement("canvas");
    canvas.width = Math.ceil(width * scale);
    canvas.height = Math.ceil(height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    return {
      dataUrl: canvas.toDataURL("image/png"),
      widthPx: canvas.width,
      heightPx: canvas.height,
      aspectRatio: canvas.width / canvas.height,
    };
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

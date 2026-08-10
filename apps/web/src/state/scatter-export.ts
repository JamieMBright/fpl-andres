/**
 * The current chart as a PNG.
 *
 * A serialised `<svg>` carries no stylesheet, so an export that just calls
 * `XMLSerializer` produces a black-on-black rectangle. Every drawn element has
 * its computed presentation copied onto it first.
 *
 * Nothing external is ever drawn into the canvas -- the chart is paths and
 * text, and player photographs deliberately stay out of it -- so the canvas
 * cannot be tainted and `toBlob` is allowed to return.
 */

const INLINED = [
  "fill",
  "fill-opacity",
  "stroke",
  "stroke-width",
  "stroke-opacity",
  "stroke-dasharray",
  "opacity",
  "paint-order",
  "font-family",
  "font-size",
  "font-weight",
  "text-anchor",
] as const;

// Two device pixels per CSS pixel, so the text is not soft when someone drops
// the export into a thread.
const SCALE = 2;

export class ScatterExportError extends Error {
  override name = "ScatterExportError";
}

function inlineStyles(source: Element, clone: Element): void {
  const computed = getComputedStyle(source);
  const raw = source.getAttribute("style") ?? "";
  const declarations = INLINED.map((property) => {
    const computedValue = computed.getPropertyValue(property);
    const explicitValue =
      source instanceof SVGElement
        ? source.style.getPropertyValue(property)
        : "";
    const rawValue =
      raw
        .split(";")
        .map((entry) => entry.split(":"))
        .find(([name]) => name?.trim() === property)?.[1]
        ?.trim() ?? "";
    return `${property}:${computedValue || explicitValue || rawValue}`;
  }).join(";");
  clone.setAttribute(
    "style",
    `${declarations};${clone.getAttribute("style") ?? ""}`,
  );

  const sourceChildren = source.children;
  const cloneChildren = clone.children;
  for (let index = 0; index < sourceChildren.length; index += 1) {
    inlineStyles(sourceChildren[index]!, cloneChildren[index]!);
  }
}

/** Test seam: the exact SVG markup handed to the browser rasteriser. */
export function serialisedScatterSvg(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  inlineStyles(svg, clone);
  const viewBox = svg.viewBox.baseVal;
  const width = viewBox.width || svg.clientWidth;
  const height = viewBox.height || svg.clientHeight;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  return new XMLSerializer().serializeToString(clone);
}

export async function scatterToPngBlob(svg: SVGSVGElement): Promise<Blob> {
  const viewBox = svg.viewBox.baseVal;
  const width = viewBox.width || svg.clientWidth;
  const height = viewBox.height || svg.clientHeight;
  const markup = serialisedScatterSvg(svg);
  const source = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;

  const image = new Image();
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () =>
      reject(new ScatterExportError("the chart would not rasterise"));
    image.src = source;
  });

  const canvas = document.createElement("canvas");
  canvas.width = width * SCALE;
  canvas.height = height * SCALE;
  const context = canvas.getContext("2d");
  if (!context) throw new ScatterExportError("this browser gave no 2D canvas");

  // The SVG background is a painted rect, but the area outside the plot is the
  // page showing through, which rasterises transparent without this.
  context.fillStyle =
    getComputedStyle(svg).getPropertyValue("background-color");
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0, canvas.width, canvas.height);

  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new ScatterExportError("the chart would not encode as PNG"));
    }, "image/png");
  });
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

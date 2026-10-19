import type { BBox, Finding } from "../api/types";

/** El backend rinde las páginas a DPI=150; las coordenadas persistidas están en puntos PDF (72 por pulgada). */
export const DPI = 150;
export const PX_PER_PT = DPI / 72;
export const HANDLE_SIZE = 9;

export interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}
export interface Point {
  x: number;
  y: number;
}
export type Handle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

export function hasBbox(f: Finding): f is Finding & { bbox_x0: number; bbox_y0: number; bbox_x1: number; bbox_y1: number } {
  return f.bbox_x0 != null && f.bbox_y0 != null && f.bbox_x1 != null && f.bbox_y1 != null;
}

export function bboxToPx(f: { bbox_x0: number; bbox_y0: number; bbox_x1: number; bbox_y1: number }): Rect {
  return { x0: f.bbox_x0 * PX_PER_PT, y0: f.bbox_y0 * PX_PER_PT, x1: f.bbox_x1 * PX_PER_PT, y1: f.bbox_y1 * PX_PER_PT };
}

/** Recorta al lienzo, ordena las esquinas y convierte de píxeles a puntos PDF. */
export function pxRectToBboxPt(rect: Rect, width: number, height: number): BBox {
  const clampX = (v: number) => Math.max(0, Math.min(v, width));
  const clampY = (v: number) => Math.max(0, Math.min(v, height));
  let x0 = clampX(rect.x0);
  let x1 = clampX(rect.x1);
  let y0 = clampY(rect.y0);
  let y1 = clampY(rect.y1);
  if (x1 < x0) [x0, x1] = [x1, x0];
  if (y1 < y0) [y0, y1] = [y1, y0];
  return { x0: x0 / PX_PER_PT, y0: y0 / PX_PER_PT, x1: x1 / PX_PER_PT, y1: y1 / PX_PER_PT };
}

export function normalizeRect(a: Point, b: Point): Rect {
  return { x0: Math.min(a.x, b.x), y0: Math.min(a.y, b.y), x1: Math.max(a.x, b.x), y1: Math.max(a.y, b.y) };
}

export function pointInRect(p: Point, r: Rect, tolerance = 0): boolean {
  return p.x >= r.x0 - tolerance && p.x <= r.x1 + tolerance && p.y >= r.y0 - tolerance && p.y <= r.y1 + tolerance;
}

export function handlePoints(r: Rect): Record<Handle, Point> {
  const mx = (r.x0 + r.x1) / 2;
  const my = (r.y0 + r.y1) / 2;
  return {
    nw: { x: r.x0, y: r.y0 },
    n: { x: mx, y: r.y0 },
    ne: { x: r.x1, y: r.y0 },
    e: { x: r.x1, y: my },
    se: { x: r.x1, y: r.y1 },
    s: { x: mx, y: r.y1 },
    sw: { x: r.x0, y: r.y1 },
    w: { x: r.x0, y: my },
  };
}

export function handleAt(p: Point, r: Rect): Handle | null {
  const pts = handlePoints(r);
  for (const key of Object.keys(pts) as Handle[]) {
    if (Math.abs(p.x - pts[key].x) <= HANDLE_SIZE && Math.abs(p.y - pts[key].y) <= HANDLE_SIZE) return key;
  }
  return null;
}

export function resizeByHandle(orig: Rect, handle: Handle, p: Point): Rect {
  const r = { ...orig };
  if (handle.includes("n")) r.y0 = p.y;
  if (handle.includes("s")) r.y1 = p.y;
  if (handle.includes("w")) r.x0 = p.x;
  if (handle.includes("e")) r.x1 = p.x;
  return r;
}

export const STATUS_COLORS: Record<string, string> = {
  cumple: "#218c21",
  no_cumple: "#cc1a1a",
  parcial: "#d98c00",
  no_determinable: "#737373",
  requiere_revision: "#0059cc",
};

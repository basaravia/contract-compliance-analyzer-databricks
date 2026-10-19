import { describe, expect, it } from "vitest";
import { PX_PER_PT, bboxToPx, handleAt, normalizeRect, pointInRect, pxRectToBboxPt, resizeByHandle } from "./geometry";

describe("geometría del visor", () => {
  it("convierte puntos PDF a píxeles y de vuelta sin perder precisión", () => {
    const f = { bbox_x0: 72, bbox_y0: 100, bbox_x1: 300, bbox_y1: 140 };
    const px = bboxToPx(f);
    expect(px.x0).toBeCloseTo(72 * PX_PER_PT);
    const back = pxRectToBboxPt(px, 2000, 2000);
    expect(back.x0).toBeCloseTo(72);
    expect(back.y1).toBeCloseTo(140);
  });

  it("recorta al lienzo y reordena esquinas invertidas", () => {
    const bbox = pxRectToBboxPt({ x0: 500, y0: 300, x1: -20, y1: 9999 }, 400, 600);
    expect(bbox.x0).toBe(0);
    expect(bbox.x1).toBeCloseTo(400 / PX_PER_PT);
    expect(bbox.y0).toBeCloseTo(300 / PX_PER_PT);
    expect(bbox.y1).toBeCloseTo(600 / PX_PER_PT);
  });

  it("normaliza un arrastre en cualquier dirección", () => {
    expect(normalizeRect({ x: 50, y: 60 }, { x: 10, y: 20 })).toEqual({ x0: 10, y0: 20, x1: 50, y1: 60 });
  });

  it("detecta asas y redimensiona solo los lados del asa", () => {
    const r = { x0: 10, y0: 10, x1: 110, y1: 60 };
    expect(handleAt({ x: 110, y: 60 }, r)).toBe("se");
    expect(handleAt({ x: 60, y: 10 }, r)).toBe("n");
    expect(handleAt({ x: 60, y: 35 }, r)).toBeNull();
    expect(resizeByHandle(r, "se", { x: 200, y: 90 })).toEqual({ x0: 10, y0: 10, x1: 200, y1: 90 });
    expect(resizeByHandle(r, "w", { x: 0, y: 999 })).toEqual({ x0: 0, y0: 10, x1: 110, y1: 60 });
  });

  it("pointInRect respeta la tolerancia", () => {
    const r = { x0: 10, y0: 10, x1: 20, y1: 20 };
    expect(pointInRect({ x: 21, y: 15 }, r)).toBe(false);
    expect(pointInRect({ x: 21, y: 15 }, r, 2)).toBe(true);
  });
});

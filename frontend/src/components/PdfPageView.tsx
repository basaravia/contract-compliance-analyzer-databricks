import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState, type ReactNode } from "react";

// El worker se empaqueta como archivo propio: la CSP del backend solo admite scripts de 'self'.
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export type PdfDoc = pdfjs.PDFDocumentProxy;

/** Abre el PDF original (no imágenes): texto nítido, seleccionable y con zoom sin pérdida. */
export function usePdfDocument(url: string): { pdf: PdfDoc | null; error: string } {
  const [state, setState] = useState<{ pdf: PdfDoc | null; error: string }>({ pdf: null, error: "" });
  useEffect(() => {
    const task = pdfjs.getDocument({ url, withCredentials: true });
    let alive = true;
    task.promise.then(
      (pdf) => alive && setState({ pdf, error: "" }),
      () => alive && setState({ pdf: null, error: "No se pudo abrir el PDF. Vuelve a cargar la página o sube el documento otra vez." }),
    );
    return () => {
      alive = false;
      void task.destroy();
    };
  }, [url]);
  return state;
}

interface Props {
  pdf: PdfDoc;
  page: number;
  /** Ancho en píxeles CSS con el que se muestra la página (ya incluye el zoom). */
  cssWidth: number;
  /** Alto/ancho de la página en puntos PDF, para que el padre ajuste su capa de dibujo. */
  onSize: (pointsWidth: number, pointsHeight: number) => void;
  /** Permite seleccionar y copiar texto (la capa de dibujo deja pasar el ratón). */
  textMode: boolean;
  /** Capas encima del PDF (rectángulos de hallazgos). */
  children: ReactNode;
}

export function PdfPageView({ pdf, page, cssWidth, onSize, textMode, children }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let renderTask: pdfjs.RenderTask | null = null;
    let textLayer: pdfjs.TextLayer | null = null;
    (async () => {
      const pdfPage = await pdf.getPage(page);
      if (cancelled) return;
      const base = pdfPage.getViewport({ scale: 1 });
      onSize(base.width, base.height);
      const scale = cssWidth / base.width;
      const viewport = pdfPage.getViewport({ scale });
      setHeight(viewport.height);

      const canvas = canvasRef.current;
      const text = textRef.current;
      if (!canvas || !text) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * dpr);
      canvas.height = Math.floor(viewport.height * dpr);
      renderTask = pdfPage.render({
        canvas,
        viewport,
        transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
      });
      try {
        await renderTask.promise;
      } catch {
        return; // render cancelado por un cambio de página o de zoom
      }
      if (cancelled) return;
      text.replaceChildren();
      text.style.setProperty("--scale-factor", String(scale));
      textLayer = new pdfjs.TextLayer({ textContentSource: pdfPage.streamTextContent(), container: text, viewport });
      await textLayer.render().catch(() => undefined);
    })();
    return () => {
      cancelled = true;
      renderTask?.cancel();
      textLayer?.cancel();
    };
  }, [pdf, page, cssWidth, onSize]);

  return (
    <div className="pdf-page" style={{ width: cssWidth, height: height || undefined }}>
      <canvas ref={canvasRef} className="pdf-canvas" />
      <div ref={textRef} className={"textLayer" + (textMode ? " text-mode" : "")} />
      {children}
    </div>
  );
}

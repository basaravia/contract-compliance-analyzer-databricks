import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "../api/client";
import { useFindingMutations } from "../api/hooks";
import {
  DPI,
  HANDLE_SIZE,
  STATUS_COLORS,
  bboxToPx,
  handleAt,
  handlePoints,
  hasBbox,
  normalizeRect,
  pointInRect,
  pxRectToBboxPt,
  resizeByHandle,
  type Handle,
  type Point,
  type Rect,
} from "../lib/geometry";
import { STATUS_LABELS, type AnalysisDetail, type DocumentOut, type Finding, type FindingStatus, type Rule } from "../api/types";

type Drag =
  | { type: "create"; start: Point; current: Point }
  | { type: "move"; id: string; orig: Rect; start: Point; preview: Rect }
  | { type: "resize"; id: string; orig: Rect; handle: Handle; preview: Rect };

interface Props {
  analysis: AnalysisDetail;
  document: DocumentOut;
  rules: Rule[];
}

function drawRect(ctx: CanvasRenderingContext2D, r: Rect, color: string, selected: boolean, dashed = false) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = selected ? 3 : 2;
  if (dashed) ctx.setLineDash([6, 4]);
  ctx.strokeRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
  ctx.globalAlpha = 0.12;
  ctx.fillStyle = color;
  ctx.fillRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
  ctx.restore();
}

function drawHandles(ctx: CanvasRenderingContext2D, r: Rect) {
  ctx.save();
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "#1d4ed8";
  ctx.lineWidth = 1.5;
  for (const p of Object.values(handlePoints(r))) {
    ctx.beginPath();
    ctx.rect(p.x - HANDLE_SIZE / 2, p.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
    ctx.fill();
    ctx.stroke();
  }
  ctx.restore();
}

export function PdfReview({ analysis, document: doc, rules }: Props) {
  const mut = useFindingMutations(analysis.id);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const dragRef = useRef<Drag | null>(null);

  const [page, setPage] = useState(1);
  const [mode, setMode] = useState<"select" | "create">("select");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pending, setPending] = useState<Rect | null>(null);
  const [newRuleId, setNewRuleId] = useState("");
  const [error, setError] = useState("");

  const ruleIds = analysis.rule_ids.length ? analysis.rule_ids : rules.map((r) => r.id);
  const ruleName = (id: string) => rules.find((r) => r.id === id)?.name ?? id;
  const onPage = analysis.findings.filter((f) => f.page === page && hasBbox(f));
  const selected = analysis.findings.find((f) => f.id === selectedId) ?? null;

  // El dibujo lee siempre los últimos valores a través de un ref: el arrastre repinta a 60 fps sin re-render de React.
  const live = useRef({ onPage, selectedId, pending });
  live.current = { onPage, selectedId, pending };

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { onPage, selectedId, pending } = live.current;
    const drag = dragRef.current;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    for (const f of onPage) {
      if (!hasBbox(f)) continue;
      const isSel = f.id === selectedId;
      const r = drag && drag.type !== "create" && drag.id === f.id ? drag.preview : bboxToPx(f);
      drawRect(ctx, r, STATUS_COLORS[f.status] ?? "#737373", isSel);
      if (isSel) drawHandles(ctx, r);
    }
    if (drag?.type === "create") drawRect(ctx, normalizeRect(drag.start, drag.current), "#1d4ed8", false, true);
    else if (pending) drawRect(ctx, pending, "#1d4ed8", true, true);
  }, []);

  // Carga la imagen de la página (la rinde el backend a DPI fijo; las coordenadas guardadas están en puntos PDF).
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      imageRef.current = img;
      redraw();
    };
    img.onerror = () => setError("No se pudo cargar la página del PDF.");
    img.src = `/api/documents/${doc.id}/pages/${page}.png?dpi=${DPI}`;
    return () => {
      img.onload = null;
      img.onerror = null;
    };
  }, [doc.id, page, redraw]);

  useEffect(redraw, [redraw, analysis.findings, selectedId, pending]);

  const pos = (e: React.PointerEvent<HTMLCanvasElement>): Point => {
    const c = canvasRef.current!;
    const b = c.getBoundingClientRect();
    return { x: ((e.clientX - b.left) * c.width) / b.width, y: ((e.clientY - b.top) * c.height) / b.height };
  };

  const select = (id: string | null) => {
    setSelectedId(id);
    setPending(null);
  };

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!imageRef.current) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    e.currentTarget.focus();
    const p = pos(e);
    setError("");
    if (mode === "create") {
      dragRef.current = { type: "create", start: p, current: p };
      return;
    }
    if (selected && selected.page === page && hasBbox(selected)) {
      const r = bboxToPx(selected);
      const handle = handleAt(p, r);
      if (handle) {
        dragRef.current = { type: "resize", id: selected.id, orig: r, handle, preview: r };
        return;
      }
      if (pointInRect(p, r)) {
        dragRef.current = { type: "move", id: selected.id, orig: r, start: p, preview: r };
        return;
      }
    }
    // Entre varios hallazgos solapados gana el más pequeño (el más específico).
    const hit = onPage
      .filter(hasBbox)
      .map((f) => ({ f, r: bboxToPx(f) }))
      .filter(({ r }) => pointInRect(p, r, 2))
      .sort((a, b) => (a.r.x1 - a.r.x0) * (a.r.y1 - a.r.y0) - (b.r.x1 - b.r.x0) * (b.r.y1 - b.r.y0))[0];
    if (hit) {
      select(hit.f.id);
      dragRef.current = { type: "move", id: hit.f.id, orig: hit.r, start: p, preview: hit.r };
    } else {
      select(null);
    }
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const d = dragRef.current;
    if (!d) return;
    const p = pos(e);
    if (d.type === "create") d.current = p;
    else if (d.type === "move") {
      const dx = p.x - d.start.x;
      const dy = p.y - d.start.y;
      d.preview = { x0: d.orig.x0 + dx, y0: d.orig.y0 + dy, x1: d.orig.x1 + dx, y1: d.orig.y1 + dy };
    } else d.preview = resizeByHandle(d.orig, d.handle, p);
    redraw();
  };

  const onPointerUp = () => {
    const d = dragRef.current;
    dragRef.current = null;
    const canvas = canvasRef.current;
    if (!d || !canvas) return;
    if (d.type === "create") {
      const r = normalizeRect(d.start, d.current);
      if (r.x1 - r.x0 < 6 || r.y1 - r.y0 < 6) return redraw();
      setNewRuleId((v) => v || ruleIds[0] || "");
      setPending(r);
      return;
    }
    // Mover/redimensionar dispara el recálculo real de la evidencia en el backend.
    mut.moveBbox.mutate(
      { id: d.id, bbox: pxRectToBboxPt(d.preview, canvas.width, canvas.height) },
      { onError: (err) => (setError(errorMessage(err)), redraw()) },
    );
  };

  const remove = (f: Finding) => {
    if (!confirm("¿Eliminar este hallazgo?")) return;
    mut.remove.mutate(f.id, {
      onSuccess: () => select(null),
      onError: (err) => setError(errorMessage(err)),
    });
  };

  const pageCount = doc.page_count;

  return (
    <div>
      <div className="review-toolbar">
        <button type="button" className="btn btn-secondary" disabled={page <= 1} onClick={() => (select(null), setPage(page - 1))}>
          ← Página anterior
        </button>
        <span>
          Página {page} / {pageCount}
        </span>
        <button type="button" className="btn btn-secondary" disabled={page >= pageCount} onClick={() => (select(null), setPage(page + 1))}>
          Página siguiente →
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          aria-pressed={mode === "create"}
          onClick={() => (setMode(mode === "create" ? "select" : "create"), select(null))}
        >
          {mode === "create" ? "Modo: crear anotación" : "Modo: seleccionar"}
        </button>
        <span className="hint">Arrastra para mover/redimensionar. En modo crear, dibuja un rectángulo nuevo. Supr elimina el seleccionado.</span>
      </div>
      {error && <p className="form-msg error" role="alert">{error}</p>}
      <div className="review-body">
        <div className="canvas-wrap">
          <canvas
            ref={canvasRef}
            className="review-canvas"
            tabIndex={0}
            aria-label={`Página ${page} del contrato con hallazgos`}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onKeyDown={(e) => {
              if ((e.key === "Delete" || e.key === "Backspace") && selected) {
                e.preventDefault();
                remove(selected);
              }
            }}
          />
        </div>
        <aside className="side-panel">
          <h3>Detalle del hallazgo</h3>
          {pending ? (
            <div>
              <h4>Nueva anotación</h4>
              <label>
                Regla
                <select value={newRuleId} onChange={(e) => setNewRuleId(e.target.value)}>
                  {ruleIds.map((id) => (
                    <option key={id} value={id}>
                      {ruleName(id)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="btn btn-primary btn-small"
                disabled={!newRuleId || mut.create.isPending}
                onClick={() =>
                  mut.create.mutate(
                    { ruleId: newRuleId, page, bbox: pxRectToBboxPt(pending, canvasRef.current!.width, canvasRef.current!.height) },
                    { onSuccess: (f) => select(f.id), onError: (err) => setError(errorMessage(err)) },
                  )
                }
              >
                Crear hallazgo
              </button>{" "}
              <button type="button" className="btn btn-secondary btn-small" onClick={() => setPending(null)}>
                Cancelar
              </button>
            </div>
          ) : selected ? (
            <FindingDetail
              key={selected.id + selected.status}
              finding={selected}
              ruleName={ruleName(selected.rule_id)}
              busy={mut.setStatus.isPending}
              onSave={(status) => mut.setStatus.mutate({ id: selected.id, status }, { onError: (err) => setError(errorMessage(err)) })}
              onDelete={() => remove(selected)}
            />
          ) : (
            <p className="hint">Selecciona un rectángulo en el PDF, o crea uno nuevo.</p>
          )}
        </aside>
      </div>
    </div>
  );
}

function FindingDetail(props: {
  finding: Finding;
  ruleName: string;
  busy: boolean;
  onSave: (s: FindingStatus) => void;
  onDelete: () => void;
}) {
  const f = props.finding;
  const [status, setStatus] = useState<FindingStatus>(f.status);
  const rows: [string, string][] = [
    ["Regla", props.ruleName],
    ["Estado", STATUS_LABELS[f.status]],
    ["Severidad", f.severity],
    ["Confianza", f.confidence.toFixed(2)],
    ["Manual", f.is_manual ? "Sí" : "No"],
    ["Editado", f.edited ? "Sí" : "No"],
    ["Página", f.page != null ? String(f.page) : "—"],
    ["Justificación", f.justification || "—"],
    ["Texto de evidencia", f.evidence_text || "(sin evidencia extraída)"],
  ];
  return (
    <div>
      <dl className="detail-list">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
        {f.normative_refs.length > 0 && (
          <div>
            <dt>Referencias normativas</dt>
            <dd>
              <ul className="ref-list">
                {f.normative_refs.map((r, i) => (
                  <li key={i}>
                    {r.citation}
                    {r.page ? ` (p. ${r.page})` : ""}
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        )}
      </dl>
      {f.trace && (
        <details className="trace-details">
          <summary>Traza del motor</summary>
          <dl>
            <dt>Método</dt>
            <dd>{f.trace.method_summary}</dd>
            <dt>Evaluador</dt>
            <dd>
              {f.trace.grader_provider}
              {f.trace.grader_model ? ` · ${f.trace.grader_model}` : ""}
            </dd>
            {f.trace.second_pass && (
              <>
                <dt>Segunda pasada</dt>
                <dd>
                  {f.trace.second_pass}
                  {f.trace.chunks_total != null ? ` (${f.trace.chunks_scanned ?? 0}/${f.trace.chunks_total} fragmentos)` : ""}
                </dd>
              </>
            )}
            {f.trace.limitations.length > 0 && (
              <>
                <dt>Limitaciones</dt>
                <dd>
                  <ul>
                    {f.trace.limitations.map((l, i) => (
                      <li key={i}>{l}</li>
                    ))}
                  </ul>
                </dd>
              </>
            )}
          </dl>
        </details>
      )}
      <label>
        Cambiar estado manualmente
        <select value={status} onChange={(e) => setStatus(e.target.value as FindingStatus)}>
          {(Object.keys(STATUS_LABELS) as FindingStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="btn btn-secondary btn-small" disabled={props.busy || status === f.status} onClick={() => props.onSave(status)}>
        Guardar estado
      </button>{" "}
      <button type="button" className="btn btn-danger btn-small" onClick={props.onDelete}>
        Eliminar hallazgo
      </button>
    </div>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, ChevronLeft, ChevronRight, Maximize2, MousePointer2, Save, SquareDashed, TextCursorInput, Trash2, ZoomIn, ZoomOut } from "lucide-react";
import { AiAssistant, certainty } from "./AiAssistant";
import { AiBadge } from "./AiBadge";
import { PdfPageView, usePdfDocument } from "./PdfPageView";
import { errorMessage } from "../api/client";
import { useFindingMutations } from "../api/hooks";
import {
  HANDLE_SIZE,
  PX_PER_PT,
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
import { STATUS_LABELS, type AnalysisDetail, type DocumentOut, type Finding, type FindingStatus, type RegionProposal, type Rule } from "../api/types";

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
  const wrapRef = useRef<HTMLDivElement>(null);
  const { pdf, error: pdfError } = usePdfDocument(`/api/documents/${doc.id}/file`);
  // Tamaño de la página en la unidad de dibujo (píxeles a 150 DPI): las coordenadas guardadas están en puntos PDF.
  const [pageSize, setPageSize] = useState<{ w: number; h: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [fitWidth, setFitWidth] = useState(700);
  const dragRef = useRef<Drag | null>(null);

  const [page, setPage] = useState(1);
  const [mode, setMode] = useState<"select" | "create" | "text">("select");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pending, setPending] = useState<Rect | null>(null);
  const [newRuleId, setNewRuleId] = useState("");
  const pendingKey = pending ? `${page}-${Math.round(pending.x0)}-${Math.round(pending.y0)}-${Math.round(pending.x1)}-${Math.round(pending.y1)}-${newRuleId}` : "";
  const [error, setError] = useState("");

  const ruleIds = analysis.rule_ids.length ? analysis.rule_ids : rules.map((r) => r.id);
  const ruleName = (id: string) => rules.find((r) => r.id === id)?.name ?? id;
  const onPage = analysis.findings.filter((f) => f.page === page && hasBbox(f));
  const selected = analysis.findings.find((f) => f.id === selectedId) ?? null;
  // Cláusulas que empiezan en otra página y continúan en esta: se dibujan discontinuas, con el color del hallazgo.
  const continuations = analysis.findings.flatMap((f) =>
    (f.extra_regions ?? []).filter((r) => r.page === page).map((r) => ({ f, rect: bboxToPx({ bbox_x0: r.x0, bbox_y0: r.y0, bbox_x1: r.x1, bbox_y1: r.y1 }) })),
  );
  // Hallazgos cuyo recuadro se movió: el estado y la justificación siguen siendo los de antes hasta reprocesar con IA.
  const [stale, setStale] = useState<Set<string>>(new Set());

  // El dibujo lee siempre los últimos valores a través de un ref: el arrastre repinta a 60 fps sin re-render de React.
  const live = useRef({ onPage, selectedId, pending, continuations });
  live.current = { onPage, selectedId, pending, continuations };

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { onPage, selectedId, pending, continuations } = live.current;
    const drag = dragRef.current;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const f of onPage) {
      if (!hasBbox(f)) continue;
      const isSel = f.id === selectedId;
      const r = drag && drag.type !== "create" && drag.id === f.id ? drag.preview : bboxToPx(f);
      drawRect(ctx, r, STATUS_COLORS[f.status] ?? "#737373", isSel);
      if (isSel) drawHandles(ctx, r);
    }
    for (const { f, rect } of continuations) drawRect(ctx, rect, STATUS_COLORS[f.status] ?? "#737373", f.id === selectedId, true);
    if (drag?.type === "create") drawRect(ctx, normalizeRect(drag.start, drag.current), "#1d4ed8", false, true);
    else if (pending) drawRect(ctx, pending, "#1d4ed8", true, true);
  }, []);

  const onPageSize = useCallback((w: number, h: number) => setPageSize({ w: Math.round(w * PX_PER_PT), h: Math.round(h * PX_PER_PT) }), []);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !pageSize) return;
    canvas.width = pageSize.w;
    canvas.height = pageSize.h;
    redraw();
  }, [pageSize, redraw]);

  // «Ajustar al ancho»: el zoom 100 % es la página ocupando todo el espacio disponible.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setFitWidth(Math.max(320, el.clientWidth - 24));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(redraw, [redraw, analysis.findings, selectedId, pending, page]);

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
    if (mode === "text") return;
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
      const cont = continuations.find(({ rect }) => pointInRect(p, rect, 2));
      select(cont ? cont.f.id : null);
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
    // Un simple clic (sin arrastrar) no cambia nada: no se guarda ni se marca como editado.
    const moved = (["x0", "y0", "x1", "y1"] as const).some((k) => Math.abs(d.preview[k] - d.orig[k]) > 1);
    if (!moved) return redraw();
    // Mover/redimensionar NO ejecuta la IA: solo guarda el recuadro y refresca el texto que contiene.
    // El auditor decide si quiere reprocesar con IA (con sus propias indicaciones) desde el panel.
    mut.moveBbox.mutate(
      { id: d.id, bbox: pxRectToBboxPt(d.preview, canvas.width, canvas.height) },
      {
        onSuccess: () => setStale((s) => new Set(s).add(d.id)),
        onError: (err) => (setError(errorMessage(err)), redraw()),
      },
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
  const goTo = (n: number) => {
    select(null);
    setPage(Math.min(pageCount, Math.max(1, n)));
  };

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<number[] | null>(null);
  const [searching, setSearching] = useState(false);
  const search = async () => {
    if (!pdf || !query.trim()) return;
    setSearching(true);
    const q = query.trim().toLowerCase();
    const found: number[] = [];
    for (let n = 1; n <= pdf.numPages; n++) {
      const content = await (await pdf.getPage(n)).getTextContent();
      if (content.items.map((it) => ("str" in it ? it.str : "")).join(" ").toLowerCase().includes(q)) found.push(n);
    }
    setHits(found);
    setSearching(false);
    if (found.length && !found.includes(page)) goTo(found[0]);
  };

  const MODE_HELP: Record<typeof mode, string> = {
    select: "Haz clic en un recuadro de color para ver el hallazgo. Arrástralo para moverlo o cambia su tamaño por las esquinas.",
    create: "Dibuja un recuadro sobre el texto que quieres registrar como hallazgo.",
    text: "Selecciona texto del contrato para copiarlo (Ctrl+C).",
  };
  const cssWidth = Math.round(fitWidth * zoom);

  return (
    <div>
      <div className="review-toolbar">
        <div className="toolbar-group" role="group" aria-label="Página">
          <button type="button" className="btn btn-secondary btn-small" disabled={page <= 1} onClick={() => goTo(page - 1)} aria-label="Página anterior">
            <ChevronLeft size={16} />
          </button>
          <label className="inline-field">
            Página
            <input
              type="number"
              min={1}
              max={pageCount}
              value={page}
              onChange={(e) => e.target.value && goTo(Number(e.target.value))}
              aria-label="Número de página"
            />
            de {pageCount}
          </label>
          <button type="button" className="btn btn-secondary btn-small" disabled={page >= pageCount} onClick={() => goTo(page + 1)} aria-label="Página siguiente">
            <ChevronRight size={16} />
          </button>
        </div>
        <div className="toolbar-group" role="group" aria-label="Zoom">
          <button type="button" className="btn btn-secondary btn-small" disabled={zoom <= 0.5} onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.25).toFixed(2)))} aria-label="Alejar">
            <ZoomOut size={16} />
          </button>
          <span className="zoom-value" aria-live="polite">{Math.round(zoom * 100)} %</span>
          <button type="button" className="btn btn-secondary btn-small" disabled={zoom >= 3} onClick={() => setZoom((z) => Math.min(3, +(z + 0.25).toFixed(2)))} aria-label="Acercar">
            <ZoomIn size={16} />
          </button>
          <button type="button" className="btn btn-secondary btn-small" onClick={() => setZoom(1)}>
            <Maximize2 size={14} /> Ajustar al ancho
          </button>
        </div>
        <div className="toolbar-group" role="group" aria-label="Herramienta">
          {(
            [
              ["select", "Ver hallazgos", MousePointer2],
              ["create", "Marcar zona", SquareDashed],
              ["text", "Copiar texto", TextCursorInput],
            ] as const
          ).map(([m, label, Icon]) => (
            <button
              key={m}
              type="button"
              className={"btn btn-small " + (mode === m ? "btn-primary" : "btn-secondary")}
              aria-pressed={mode === m}
              onClick={() => (setMode(m), select(null))}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
        <form
          className="toolbar-group"
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            void search();
          }}
        >
          <input type="search" placeholder="Buscar en el contrato" aria-label="Buscar en el contrato" value={query} onChange={(e) => (setQuery(e.target.value), setHits(null))} />
          <button type="submit" className="btn btn-secondary btn-small" disabled={searching || !query.trim() || !pdf}>
            {searching ? "Buscando…" : "Buscar"}
          </button>
        </form>
      </div>
      <p className="hint" role="status">
        {hits
          ? hits.length
            ? <>Encontrado en {hits.length === 1 ? "la página" : "las páginas"}:{" "}
                {hits.map((n) => (
                  <button key={n} type="button" className="link-btn hit" onClick={() => goTo(n)}>{n}</button>
                ))}</>
            : "No se encontró ese texto en el contrato."
          : MODE_HELP[mode]}
      </p>
      {(error || pdfError) && <p className="form-msg error" role="alert">{error || pdfError}</p>}
      <div className="review-body">
        <div className="canvas-wrap" ref={wrapRef}>
          {pdf ? (
            <PdfPageView pdf={pdf} page={page} cssWidth={cssWidth} onSize={onPageSize} textMode={mode === "text"}>
              <canvas
                ref={canvasRef}
                className={"review-canvas" + (mode === "text" ? " passthrough" : "")}
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
            </PdfPageView>
          ) : (
            !pdfError && <p className="hint on-dark">Abriendo el contrato…</p>
          )}
        </div>
        <aside className="side-panel">
          <h3>Detalle del hallazgo</h3>
          {pending ? (
            <div>
              <h4>Nueva anotación</h4>
              <label>
                Criterio
                <select value={newRuleId} onChange={(e) => setNewRuleId(e.target.value)}>
                  {ruleIds.map((id) => (
                    <option key={id} value={id}>
                      {ruleName(id)}
                    </option>
                  ))}
                </select>
              </label>
              <AiAssistant
                key={pendingKey}
                acceptLabel="Aceptar y guardar el hallazgo"
                analyze={(instructions, deep) =>
                  mut.analyze.mutateAsync({ ruleId: newRuleId, page, bbox: pxRectToBboxPt(pending, canvasRef.current!.width, canvasRef.current!.height), instructions, deep })
                }
                accept={async (proposal, instructions) => {
                  const f = await mut.create.mutateAsync({
                    ruleId: newRuleId,
                    page,
                    bbox: pxRectToBboxPt(pending, canvasRef.current!.width, canvasRef.current!.height),
                    proposal,
                    instructions,
                  });
                  select(f.id);
                }}
              />
              <p className="hint">¿Prefieres registrarlo tú mismo? Guárdalo sin IA y decide el resultado después.</p>
              <button
                type="button"
                className="btn btn-secondary btn-small"
                disabled={!newRuleId || mut.create.isPending}
                onClick={() =>
                  mut.create.mutate(
                    { ruleId: newRuleId, page, bbox: pxRectToBboxPt(pending, canvasRef.current!.width, canvasRef.current!.height) },
                    { onSuccess: (f) => select(f.id), onError: (err) => setError(errorMessage(err)) },
                  )
                }
              >
                Guardar sin IA
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
              staleBox={stale.has(selected.id)}
              analyze={(instructions, deep) =>
                mut.analyze.mutateAsync({
                  ruleId: selected.rule_id,
                  page: selected.page ?? page,
                  bbox: { x0: selected.bbox_x0!, y0: selected.bbox_y0!, x1: selected.bbox_x1!, y1: selected.bbox_y1! },
                  instructions,
                  deep,
                })
              }
              apply={async (proposal, instructions) => {
                const out = await mut.applyProposal.mutateAsync({ id: selected.id, proposal, instructions });
                setStale((s) => {
                  const n = new Set(s);
                  n.delete(selected.id);
                  return n;
                });
                return out;
              }}
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
  staleBox?: boolean;
  analyze: (instructions: string, deep: boolean) => Promise<RegionProposal>;
  apply: (proposal: RegionProposal, instructions: string) => Promise<unknown>;
}) {
  const f = props.finding;
  const extraPages = (f.extra_regions ?? []).map((r) => r.page);
  const [status, setStatus] = useState<FindingStatus>(f.status);
  const rows: [string, string][] = [
    ["Criterio", props.ruleName],
    ["Estado", STATUS_LABELS[f.status]],
    ["Importancia", f.severity],
    ["Nivel de certeza", certainty(f.confidence)],
    ["Manual", f.is_manual ? "Sí" : "No"],
    ["Editado", f.edited ? "Sí" : "No"],
    ["Página", f.page != null ? [f.page, ...extraPages.filter((p) => p !== f.page)].join(", ") + (extraPages.length ? " (la cláusula continúa)" : "") : "—"],
    ["Justificación", f.justification || "—"],
    ["Texto de evidencia", f.evidence_text || "(sin evidencia extraída)"],
  ];
  return (
    <div>
      <dl className="detail-list">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>
              {k} {k === "Justificación" && !f.is_manual && !f.edited && <AiBadge />}
            </dt>
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
      {props.staleBox && (
        <div className="notice info" role="status">
          <p>
            <strong>Cambiaste el recuadro.</strong> El texto de evidencia se actualizó, pero el estado y la justificación siguen siendo los de antes.
          </p>
          <button
            type="button"
            className="btn btn-ai btn-small"
            onClick={() => {
              const box = document.getElementById("ai-instructions");
              box?.scrollIntoView({ block: "center", behavior: "smooth" });
              box?.focus();
            }}
          >
            <Sparkles size={14} /> Reprocesar con IA
          </button>
        </div>
      )}
      {hasBbox(f) && (
        <details className="ai-details" open={!!f.ai_instructions || !!props.staleBox}>
          <summary>
            <Sparkles size={14} aria-hidden="true" /> Reprocesar este recuadro con IA
          </summary>
          <AiAssistant
            key={f.id + f.updated_at}
            reprocess
            attention={!!props.staleBox}
            initialInstructions={f.ai_instructions ?? ""}
            acceptLabel="Aceptar y aplicar al hallazgo"
            analyze={props.analyze}
            accept={props.apply}
          />
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
        <Save size={14} /> Guardar estado
      </button>{" "}
      <button type="button" className="btn btn-danger btn-small" onClick={props.onDelete}>
        <Trash2 size={14} /> Eliminar hallazgo
      </button>
    </div>
  );
}

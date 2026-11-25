import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import { ChevronDown, ChevronRight, ChevronsDownUp, ChevronsUpDown, Eye, FileDown, FileSpreadsheet, Play, RefreshCw, ScanSearch } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { download, errorMessage } from "../api/client";
import { useAnalyses, useAnalysis, useAnalysisProgress, useDocuments, useRules, useRunAnalysis } from "../api/hooks";
import { ANALYSIS_STATUS_LABELS, SEVERITY_LABELS, STATUS_HELP, STATUS_LABELS, type FindingStatus } from "../api/types";
import { certainty } from "../components/AiAssistant";
import { AiBadge } from "../components/AiBadge";
import { AnalysisProgressPanel } from "../components/AnalysisProgressPanel";
import { ProgressBar } from "../components/ProgressBar";
import { StatusPill } from "../components/StatusPill";

/** Mientras el análisis corre se muestra su avance; al terminar se recargan los hallazgos y la lista. */
function RunningCard({ id }: { id: string }) {
  const qc = useQueryClient();
  const progress = useAnalysisProgress(id, true);
  const status = progress.data?.status;

  useEffect(() => {
    if (status && status !== "running") {
      qc.invalidateQueries({ queryKey: ["analysis", id] });
      qc.invalidateQueries({ queryKey: ["analyses"] });
    }
  }, [status, id, qc]);

  return (
    <div className="card">
      <h2>Análisis en curso</h2>
      {progress.data?.live ? (
        <AnalysisProgressPanel live={progress.data.live} />
      ) : (
        <>
          <ProgressBar label="Avance del análisis" />
          <p className="loading" role="status">Iniciando…</p>
        </>
      )}
      {progress.error && <p className="form-msg error">No se pudo consultar el avance: {errorMessage(progress.error)}</p>}
    </div>
  );
}

function FindingsCard({ id }: { id: string }) {
  const analysis = useAnalysis(id);
  const rules = useRules();
  const ruleName = (rid: string) => rules.data?.find((r) => r.id === rid)?.name ?? rid;
  const [exportError, setExportError] = useState("");
  // Filas con la justificación desplegada. Texto largo en una celda de tabla ensancha todo: va en un detalle plegable.
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggleRow = (fid: string) =>
    setOpen((cur) => {
      const next = new Set(cur);
      if (!next.delete(fid)) next.add(fid);
      return next;
    });

  const save = (path: string, filename: string) =>
    download(`/api/analyses/${id}/${path}`, filename).then(
      () => setExportError(""),
      (e) => setExportError(errorMessage(e)),
    );

  if (analysis.isPending) return <p className="loading" role="status">Cargando análisis…</p>;
  if (analysis.error) return <p className="form-msg error" role="alert">{errorMessage(analysis.error)}</p>;
  const a = analysis.data;
  if (a.status === "running") return <RunningCard id={id} />;

  const counts = (Object.keys(STATUS_LABELS) as FindingStatus[])
    .map((k) => ({ k, n: a.findings.filter((f) => f.status === k).length }))
    .filter((c) => c.n > 0);

  return (
    <div className="card">
      <div className="card-header-row">
        <h2>Resultados del análisis</h2>
        <div className="export-buttons">
          <Link className="btn btn-primary" to={`/analisis/${id}/revision`}>
            <ScanSearch size={16} /> Revisar en el PDF
          </Link>
          <button type="button" className="btn btn-secondary" onClick={() => save("papel-trabajo.xlsx", `papel-trabajo-${id}.xlsx`)}>
            <FileSpreadsheet size={16} /> Papel de trabajo (Excel)
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => save("export.pdf", `analisis-${id}.pdf`)}>
            <FileDown size={16} /> PDF con marcas
          </button>
        </div>
      </div>
      {exportError && <p className="form-msg error" role="alert">{exportError}</p>}
      {a.error_message && <p className="form-msg error" role="alert">{a.error_message}</p>}
      {a.status === "interrupted" && <p className="form-msg error">Este análisis se interrumpió. Vuelve a ejecutarlo.</p>}
      <ul className="summary-chips" aria-label="Resumen de resultados">
        {counts.map(({ k, n }) => (
          <li key={k}>
            <StatusPill status={k} /> <strong>{n}</strong>
          </li>
        ))}
      </ul>
      <p className="hint">Pulsa «Revisar en el PDF» para ver cada hallazgo marcado en el contrato, corregirlo o analizarlo de nuevo con IA.</p>
      <div className="table-tools">
        <button
          type="button"
          className="link-btn"
          onClick={() => setOpen(open.size === a.findings.length ? new Set() : new Set(a.findings.map((f) => f.id)))}
        >
          {open.size === a.findings.length ? <ChevronsDownUp size={14} /> : <ChevronsUpDown size={14} />}{" "}
          {open.size === a.findings.length ? "Contraer todas las justificaciones" : "Expandir todas las justificaciones"}
        </button>
      </div>
      <table className="data-table results-table">
        <thead>
          <tr>
            <th>Criterio y justificación</th>
            <th>Resultado</th>
            <th>Importancia</th>
            <th>
              Nivel de certeza <span className="info" title="Qué tan segura está la IA de su resultado. Con certeza Baja conviene revisarlo en el PDF.">ⓘ</span>
            </th>
            <th>Página</th>
          </tr>
        </thead>
        <tbody>
          {a.findings.map((f) => {
            const isOpen = open.has(f.id);
            const pages = [f.page, ...(f.extra_regions ?? []).map((r) => r.page)].filter((p, i, arr): p is number => p != null && arr.indexOf(p) === i);
            const warnings = (f.trace?.limitations ?? []).filter((l) => l.includes("no se encontró en el documento"));
            return (
              <Fragment key={f.id}>
                <tr className={isOpen ? "row-open" : ""}>
                  <td>
                    <button
                      type="button"
                      className="row-toggle"
                      aria-expanded={isOpen}
                      aria-controls={`just-${f.id}`}
                      onClick={() => toggleRow(f.id)}
                    >
                      {isOpen ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
                      <span className="row-toggle-text">
                        <span className="row-title">{ruleName(f.rule_id)}</span>
                        {!isOpen && f.justification && <span className="row-preview">{f.justification}</span>}
                      </span>
                    </button>
                  </td>
                  <td>
                    <StatusPill status={f.status} />
                    {(f.is_manual || f.edited) && <span className="tag">{f.is_manual ? "agregado por ti" : "corregido por ti"}</span>}
                  </td>
                  <td>{SEVERITY_LABELS[f.severity] ?? f.severity}</td>
                  <td>{certainty(f.confidence)}</td>
                  <td>{pages.length ? pages.join("–") : "—"}</td>
                </tr>
                {isOpen && (
                  <tr className="detail-row" id={`just-${f.id}`}>
                    <td colSpan={5}>
                      <div className="detail-block">
                        <p className="detail-label">
                          Justificación {!f.is_manual && !f.edited && <AiBadge />}
                        </p>
                        <p className="detail-text">{f.justification || "—"}</p>
                        {f.evidence_text && (
                          <>
                            <p className="detail-label">Evidencia en el contrato{pages.length ? ` (p. ${pages.join("–")})` : ""}</p>
                            <blockquote className="evidence">{f.evidence_text}</blockquote>
                          </>
                        )}
                        {warnings.length > 0 && (
                          <div className="notice warn">
                            <ul>
                              {warnings.map((w, i) => (
                                <li key={i}>{w}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      <details className="help">
        <summary>¿Cómo leer los resultados?</summary>
        <dl>
          {(Object.keys(STATUS_LABELS) as FindingStatus[]).map((k) => (
            <div key={k}>
              <dt><StatusPill status={k} /></dt>
              <dd>{STATUS_HELP[k]}</dd>
            </div>
          ))}
        </dl>
        <p className="hint">La IA propone y tú decides: todo resultado se puede corregir en el PDF. El papel de trabajo en Excel recoge el resultado final.</p>
        <button type="button" className="link-btn" onClick={() => save("export.json", `analisis-${id}.json`)}>
          Descargar datos técnicos (JSON)
        </button>
      </details>
    </div>
  );
}

export function AnalysisPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const docs = useDocuments();
  const rules = useRules();
  const analyses = useAnalyses();
  const run = useRunAnalysis();
  const [contractId, setContractId] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [msg, setMsg] = useState<{ text: string; kind: "" | "error" | "success" }>({ text: "", kind: "" });

  const contracts = (docs.data ?? []).filter((d) => d.doc_type === "contrato");
  const activeRules = (rules.data ?? []).filter((r) => r.active);
  const docTitle = (docId: string) => {
    const d = docs.data?.find((x) => x.id === docId);
    return d ? (d.title ?? d.original_filename) : docId;
  };

  const allRef = useRef<HTMLInputElement>(null);
  const allMarked = activeRules.length > 0 && activeRules.every((r) => selected.has(r.id));
  const someMarked = !allMarked && activeRules.some((r) => selected.has(r.id));
  useEffect(() => {
    if (allRef.current) allRef.current.indeterminate = someMarked;
  }, [someMarked]);
  const toggleAll = () => setSelected(allMarked ? new Set() : new Set(activeRules.map((r) => r.id)));

  const toggle = (rid: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (!next.delete(rid)) next.add(rid);
      return next;
    });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const target = contractId || contracts[0]?.id;
    if (!target) return setMsg({ text: "Sube un contrato primero.", kind: "error" });
    setMsg({ text: "", kind: "" });
    try {
      // El servidor responde al instante; el avance se sigue en la tarjeta del análisis.
      const a = await run.mutateAsync({ contractId: target, ruleIds: [...selected] });
      navigate(`/analisis/${a.id}`);
    } catch (err) {
      setMsg({ text: errorMessage(err), kind: "error" });
    }
  };

  return (
    <>
      <div className="grid-2">
        <div className="card">
          <h2>Nuevo análisis</h2>
          {contracts.length === 0 && (
            <p className="empty">Primero sube un contrato en <Link to="/documentos">1. Documentos</Link>.</p>
          )}
          {contracts.length > 0 && activeRules.length === 0 && (
            <p className="empty">Aún no hay criterios activos. Cárgalos en <Link to="/reglas">2. Criterios</Link>.</p>
          )}
          <form onSubmit={submit}>
            <label>
              Contrato
              <select value={contractId || contracts[0]?.id || ""} onChange={(e) => setContractId(e.target.value)} required>
                {contracts.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title ?? d.original_filename}
                  </option>
                ))}
              </select>
            </label>
            <fieldset>
              <legend>Criterios a evaluar <span className="optional">(si no marcas ninguno, se usan todos los activos)</span></legend>
              {activeRules.length > 0 && (
                <div className="select-all-row">
                  <label className="inline-check">
                    <input ref={allRef} type="checkbox" checked={allMarked} onChange={toggleAll} />
                    <strong>{allMarked ? "Desmarcar todos" : "Marcar todos"}</strong>
                  </label>
                  <span className="hint" aria-live="polite">
                    {selected.size === 0 ? `Ninguno marcado: se evaluarán los ${activeRules.length}` : `${selected.size} de ${activeRules.length} marcados`}
                  </span>
                </div>
              )}
              <div className="checkbox-list">
                {activeRules.map((r) => (
                  <label key={r.id}>
                    <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} /> {r.name}
                  </label>
                ))}
              </div>
            </fieldset>
            <button type="submit" className="btn btn-primary" disabled={run.isPending}>
              {run.isPending ? "Iniciando…" : <><Play size={16} /> Ejecutar análisis</>}
            </button>
            <p className={"form-msg " + msg.kind} role="status">
              {msg.text}
            </p>
          </form>
        </div>
        <div className="card">
          <h2>Análisis anteriores</h2>
          <button type="button" className="btn btn-secondary" onClick={() => analyses.refetch()}>
            <RefreshCw size={16} /> Actualizar
          </button>
          <table className="data-table">
            <thead>
              <tr>
                <th>Contrato</th>
                <th>Estado</th>
                <th>Fecha</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(analyses.data ?? []).map((a) => (
                <tr key={a.id}>
                  <td>{docTitle(a.contract_document_id)}</td>
                  <td>{ANALYSIS_STATUS_LABELS[a.status] ?? a.status}</td>
                  <td>{new Date(a.created_at).toLocaleString()}</td>
                  <td>
                    <Link className="btn btn-secondary btn-small" to={`/analisis/${a.id}`}>
                      <Eye size={14} /> Ver
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {id && <FindingsCard key={id} id={id} />}
    </>
  );
}

import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { download, errorMessage } from "../api/client";
import { useAnalyses, useAnalysis, useAnalysisProgress, useDocuments, useRules, useRunAnalysis } from "../api/hooks";
import { ANALYSIS_STATUS_LABELS } from "../api/types";
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
          <p className="hint">Iniciando…</p>
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

  const save = (path: string, filename: string) =>
    download(`/api/analyses/${id}/${path}`, filename).then(
      () => setExportError(""),
      (e) => setExportError(errorMessage(e)),
    );

  if (analysis.isPending) return <p className="hint">Cargando análisis…</p>;
  if (analysis.error) return <p className="form-msg error">{errorMessage(analysis.error)}</p>;
  const a = analysis.data;
  if (a.status === "running") return <RunningCard id={id} />;

  return (
    <div className="card">
      <div className="card-header-row">
        <h2>Hallazgos del análisis</h2>
        <div className="export-buttons">
          <button type="button" className="btn btn-secondary" onClick={() => save("export.pdf", `analisis-${id}.pdf`)}>
            Descargar PDF anotado
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => save("export.json", `analisis-${id}.json`)}>
            Descargar JSON
          </button>
          <button type="button" className="btn btn-primary" onClick={() => save("papel-trabajo.xlsx", `papel-trabajo-${id}.xlsx`)}>
            Descargar papel de trabajo (Excel)
          </button>
          <Link className="btn btn-primary" to={`/analisis/${id}/revision`}>
            Abrir revisión visual
          </Link>
        </div>
      </div>
      {exportError && <p className="form-msg error">{exportError}</p>}
      {a.error_message && <p className="form-msg error">{a.error_message}</p>}
      <table className="data-table">
        <thead>
          <tr>
            <th>Regla</th>
            <th>Estado</th>
            <th>Severidad</th>
            <th>Confianza</th>
            <th>Manual</th>
            <th>Editado</th>
            <th>Página</th>
            <th>Traza</th>
          </tr>
        </thead>
        <tbody>
          {a.findings.map((f) => (
            <tr key={f.id}>
              <td>{ruleName(f.rule_id)}</td>
              <td>
                <StatusPill status={f.status} />
              </td>
              <td>{f.severity}</td>
              <td>{f.confidence.toFixed(2)}</td>
              <td>{f.is_manual ? "Sí" : "No"}</td>
              <td>{f.edited ? "Sí" : "No"}</td>
              <td>{f.page ?? "—"}</td>
              <td>{f.trace?.method_summary ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
              <legend>Reglas a evaluar (ninguna marcada = todas las activas)</legend>
              <div className="checkbox-list">
                {activeRules.map((r) => (
                  <label key={r.id}>
                    <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} /> {r.name}
                  </label>
                ))}
              </div>
            </fieldset>
            <button type="submit" className="btn btn-primary" disabled={run.isPending}>
              {run.isPending ? "Iniciando…" : "Ejecutar análisis"}
            </button>
            <p className={"form-msg " + msg.kind} role="status">
              {msg.text}
            </p>
          </form>
        </div>
        <div className="card">
          <h2>Análisis existentes</h2>
          <button type="button" className="btn btn-secondary" onClick={() => analyses.refetch()}>
            Actualizar
          </button>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Contrato</th>
                <th>Estado</th>
                <th>Creado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(analyses.data ?? []).map((a) => (
                <tr key={a.id}>
                  <td>{a.id.slice(0, 8)}</td>
                  <td>{docTitle(a.contract_document_id)}</td>
                  <td>{ANALYSIS_STATUS_LABELS[a.status] ?? a.status}</td>
                  <td>{new Date(a.created_at).toLocaleString()}</td>
                  <td>
                    <Link className="btn btn-secondary btn-small" to={`/analisis/${a.id}`}>
                      Ver
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

import { useState } from "react";
import { ArrowLeft, ArrowRight, CircleCheck, ClipboardPaste, Download, FileJson, FileSpreadsheet, ListChecks, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { download, errorMessage } from "../api/client";
import { useImportRules, usePreviewRules } from "../api/hooks";
import type { RulePreview } from "../api/types";

const EXAMPLE = `Regla: Protección de datos personales
Descripción: El contrato debe incluir una cláusula de tratamiento de datos.
Severidad: alta
Referencia: LOPDP Art. 5
---
Regla: Plazo de notificación de incidentes
Descripción: El contrato debe fijar un plazo máximo de notificación.
Referencia: LOPDP Art. 44`;

type Source = "excel" | "texto" | "json";
const STEPS = ["Elegir cómo cargar", "Revisar", "Listo"];

/** Carga de criterios en 3 pasos: elegir → revisar (vista previa con errores por fila) → listo. */
export function RuleImportWizard() {
  const preview = usePreviewRules();
  const imp = useImportRules();
  const [step, setStep] = useState(0);
  const [source, setSource] = useState<Source>("excel");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [result, setResult] = useState<RulePreview | null>(null);
  const [message, setMessage] = useState("");
  const [done, setDone] = useState(0);

  const needsFile = source !== "texto";
  const ready = needsFile ? !!file : !!text.trim();

  const review = async () => {
    setMessage("");
    try {
      setResult(await preview.mutateAsync(needsFile ? { kind: "file", file: file! } : { kind: "text", text }));
      setStep(1);
    } catch (e) {
      setMessage(errorMessage(e));
    }
  };

  const confirm = async () => {
    if (!result) return;
    setMessage("");
    try {
      const created = await imp.mutateAsync({ kind: "json", payload: { rules: result.rules } });
      setDone(created.length);
      setStep(2);
    } catch (e) {
      setMessage(errorMessage(e));
    }
  };

  const restart = () => {
    setStep(0);
    setResult(null);
    setFile(null);
    setText("");
    setMessage("");
  };

  return (
    <div className="card">
      <h2>Cargar varios criterios a la vez</h2>
      <ol className="steps wizard-steps" aria-label="Pasos">
        {STEPS.map((name, i) => (
          <li key={name} className={i < step ? "done" : i === step ? "current" : ""} aria-current={i === step ? "step" : undefined}>
            {name}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <>
          <div className="toolbar-group source-picker" role="group" aria-label="Formato de origen">
            {(
              [
                ["excel", "Excel (recomendado)", FileSpreadsheet],
                ["texto", "Pegar texto", ClipboardPaste],
                ["json", "Archivo JSON", FileJson],
              ] as const
            ).map(([s, label, Icon]) => (
              <button key={s} type="button" aria-pressed={source === s} className={"btn btn-small " + (source === s ? "btn-primary" : "btn-secondary")} onClick={() => (setSource(s), setFile(null), setMessage(""))}>
                <Icon size={14} /> {label}
              </button>
            ))}
          </div>

          {source === "excel" && (
            <div className="source-panel">
              <p>
                <strong>1.</strong> Descarga la plantilla, escribe un criterio por fila y guárdala.
                <br />
                <button type="button" className="btn btn-secondary btn-small" onClick={() => download("/api/rules/template.xlsx", "plantilla-criterios.xlsx").catch((e) => setMessage(errorMessage(e)))}>
                  <Download size={14} /> Descargar plantilla de Excel
                </button>
              </p>
              <p>
                <strong>2.</strong> Sube el archivo.
              </p>
            </div>
          )}
          {source === "texto" && (
            <div className="source-panel">
              <p className="hint">Un criterio por bloque, separados por una línea con <code>---</code>. Obligatorios: «Regla» y «Descripción».</p>
              <details>
                <summary>Ver un ejemplo</summary>
                <pre className="example-block">{EXAMPLE}</pre>
              </details>
              <textarea rows={8} aria-label="Texto de criterios" placeholder="Pega aquí los criterios…" value={text} onChange={(e) => setText(e.target.value)} />
            </div>
          )}
          {source === "json" && <p className="hint source-panel">Para equipos técnicos: un archivo JSON con la lista de criterios.</p>}
          {needsFile && (
            <label className="file-pick">
              {source === "excel" ? "Archivo de Excel (.xlsx)" : "Archivo JSON (.json)"}
              <input
                type="file"
                key={source}
                accept={source === "excel" ? ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" : ".json,application/json"}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          )}
          <button type="button" className="btn btn-primary" disabled={!ready || preview.isPending} onClick={review}>
            {preview.isPending ? "Revisando…" : <><ListChecks size={16} /> Revisar antes de cargar</>}
          </button>
          {message && <p className="form-msg error" role="alert">{message}</p>}
        </>
      )}

      {step === 1 && result && (
        <>
          <p role="status">
            <strong>{result.rules.length}</strong> {result.rules.length === 1 ? "criterio listo" : "criterios listos"} para cargar
            {result.errors.length > 0 && <>, <strong className="warn">{result.errors.length}</strong> {result.errors.length === 1 ? "problema" : "problemas"} por corregir</>}.
          </p>
          {result.errors.length > 0 && (
            <div className="notice warn" role="alert">
              <p><strong>Corrige esto en tu archivo y vuelve a subirlo</strong> (o carga solo los que están bien):</p>
              <ul>
                {result.errors.map((x, i) => (
                  <li key={i}><strong>{x.ref}:</strong> {x.error}</li>
                ))}
              </ul>
            </div>
          )}
          {result.rules.length > 0 && (
            <table className="data-table">
              <thead>
                <tr><th>Criterio</th><th>Importancia</th><th>Referencias</th></tr>
              </thead>
              <tbody>
                {result.rules.map((r, i) => (
                  <tr key={i}>
                    <td>{r.name}</td>
                    <td>{r.severity}</td>
                    <td>{r.references?.map((x) => x.citation).join("; ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt">
            <button type="button" className="btn btn-primary" disabled={result.rules.length === 0 || imp.isPending} onClick={confirm}>
              {imp.isPending ? "Cargando…" : `Cargar ${result.rules.length} ${result.rules.length === 1 ? "criterio" : "criterios"}`}
            </button>{" "}
            <button type="button" className="btn btn-secondary" onClick={restart}>
              <ArrowLeft size={16} /> Volver y corregir
            </button>
          </p>
          {message && <p className="form-msg error" role="alert">{message}</p>}
        </>
      )}

      {step === 2 && (
        <>
          <p className="form-msg success" role="status"><CircleCheck size={16} className="inline-icon" /> Se cargaron {done} {done === 1 ? "criterio" : "criterios"}. Ya aparecen en la lista de abajo.</p>
          <button type="button" className="btn btn-secondary" onClick={restart}><Upload size={16} /> Cargar más</button>{" "}
          <Link className="btn btn-primary" to="/analisis">Ir a analizar un contrato <ArrowRight size={16} /></Link>
        </>
      )}
    </div>
  );
}

import { Sparkles, X } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../api/client";
import type { RegionProposal } from "../api/types";
import { AiBadge } from "./AiBadge";
import { ProgressBar } from "./ProgressBar";
import { StatusPill } from "./StatusPill";

export function certainty(confidence: number): string {
  return confidence >= 0.75 ? "Alta" : confidence >= 0.5 ? "Media" : "Baja";
}

/** Atajos para afinar el análisis: añaden una indicación lista al cuadro de texto. */
const SUGGESTIONS = [
  { label: "Análisis a fondo", text: "Analiza a fondo y justifica cada punto con la frase exacta del contrato." },
  { label: "Cláusulas relacionadas", text: "Considera también las cláusulas a las que remite este texto." },
  { label: "Más estricto", text: "Sé estricto: marca como incumplimiento cualquier excepción o ambigüedad." },
];

interface Props {
  /** Pide la propuesta de la IA para el recuadro actual con las indicaciones del auditor. */
  analyze: (instructions: string, deep: boolean) => Promise<RegionProposal>;
  /** El auditor acepta la propuesta: quien llama la guarda. */
  accept: (proposal: RegionProposal, instructions: string) => Promise<unknown>;
  acceptLabel: string;
  initialInstructions?: string;
  /** Texto del botón principal cuando ya hay un resultado previo («Reprocesar con IA»). */
  reprocess?: boolean;
  /** Resalta el bloque (p. ej. tras cambiar el recuadro) para invitar a reprocesar. */
  attention?: boolean;
}

/** «Analizar con IA»: el modelo propone, la persona decide. Nada se envía ni se guarda sin pulsar el botón. */
export function AiAssistant({ analyze, accept, acceptLabel, initialInstructions = "", reprocess = false, attention = false }: Props) {
  const [instructions, setInstructions] = useState(initialInstructions);
  const [deep, setDeep] = useState(false);
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<RegionProposal | null>(null);
  const [error, setError] = useState("");

  const run = async () => {
    setBusy(true);
    setError("");
    setProposal(null);
    try {
      setProposal(await analyze(instructions, deep));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!proposal) return;
    setBusy(true);
    try {
      await accept(proposal, instructions);
      setProposal(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const addSuggestion = (text: string) => setInstructions((v) => (v.includes(text) ? v : (v.trim() ? v.trim() + " " : "") + text));
  const idleLabel = reprocess ? "Reprocesar con IA" : "Analizar con IA";

  return (
    <div className={"ai-box" + (busy && !proposal ? " is-thinking" : "") + (attention ? " needs-attention" : "")}>
      <p className="ai-box-title">
        <AiBadge>Asistente de IA</AiBadge>
      </p>
      <label>
        Indicaciones para la IA <span className="optional">(opcional)</span>
        <textarea
          id="ai-instructions"
          rows={3}
          maxLength={1000}
          placeholder="Ej.: considera solo plazos en días hábiles, o revisa con más detalle las excepciones"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </label>
      <div className="chip-row" role="group" aria-label="Indicaciones sugeridas">
        {SUGGESTIONS.map((s) => (
          <button key={s.label} type="button" className="chip" title={s.text} onClick={() => addSuggestion(s.text)} disabled={busy}>
            + {s.label}
          </button>
        ))}
      </div>
      <label className="inline-check">
        <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} /> Más contexto: incluir la cláusula completa y las que cita
      </label>
      <p className="hint ai-consent">Al pulsar el botón, el texto del recuadro (y el contexto elegido) se envía al modelo de IA. Nada se guarda hasta que aceptes la propuesta.</p>
      <button type="button" className="btn btn-ai btn-small" disabled={busy} onClick={run}>
        {busy && !proposal ? "Analizando…" : proposal ? "Analizar de nuevo" : <><Sparkles size={14} /> {idleLabel}</>}
      </button>
      {busy && !proposal && (
        <>
          <ProgressBar label="Analizando con IA" />
          <p className="hint" role="status">La IA está leyendo el texto del recuadro…</p>
        </>
      )}
      {error && <p className="form-msg error" role="alert">{error}</p>}
      {proposal && (
        <div className="proposal" role="status">
          <p className="proposal-title">
            <AiBadge>Propuesta de la IA</AiBadge> <span className="optional">— revísala antes de aceptarla</span>
          </p>
          <p>
            <StatusPill status={proposal.status} /> <span className="hint">Nivel de certeza: {certainty(proposal.confidence)}</span>
          </p>
          {!proposal.has_text && <p className="form-msg error">El recuadro no contiene texto que se pueda leer (¿zona escaneada o vacía?). Ajusta el recuadro.</p>}
          <p>{proposal.justification}</p>
          {proposal.evidence_text && <blockquote className="evidence">{proposal.evidence_text}</blockquote>}
          <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={save}>
            {acceptLabel}
          </button>{" "}
          <button type="button" className="btn btn-secondary btn-small" disabled={busy} onClick={() => setProposal(null)}>
            <X size={14} /> Descartar
          </button>
        </div>
      )}
    </div>
  );
}

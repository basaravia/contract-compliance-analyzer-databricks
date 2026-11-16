import { useState } from "react";
import { errorMessage } from "../api/client";
import type { RegionProposal } from "../api/types";
import { ProgressBar } from "./ProgressBar";
import { StatusPill } from "./StatusPill";

export function certainty(confidence: number): string {
  return confidence >= 0.75 ? "Alta" : confidence >= 0.5 ? "Media" : "Baja";
}

interface Props {
  /** Pide la propuesta de la IA para el recuadro actual con las indicaciones del auditor. */
  analyze: (instructions: string) => Promise<RegionProposal>;
  /** El auditor acepta la propuesta: quien llama la guarda. */
  accept: (proposal: RegionProposal, instructions: string) => Promise<unknown>;
  acceptLabel: string;
  initialInstructions?: string;
}

/** «Analizar con IA»: el modelo propone, la persona decide. Nada se guarda hasta pulsar «Aceptar». */
export function AiAssistant({ analyze, accept, acceptLabel, initialInstructions = "" }: Props) {
  const [instructions, setInstructions] = useState(initialInstructions);
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<RegionProposal | null>(null);
  const [error, setError] = useState("");

  const run = async () => {
    setBusy(true);
    setError("");
    setProposal(null);
    try {
      setProposal(await analyze(instructions));
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

  return (
    <div className="ai-box">
      <label>
        Indicaciones para la IA <span className="optional">(opcional)</span>
        <textarea
          rows={2}
          maxLength={1000}
          placeholder="Ej.: considera solo plazos en días hábiles"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </label>
      <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={run}>
        {busy && !proposal ? "Analizando…" : proposal ? "Analizar de nuevo" : "Analizar con IA"}
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
          <p className="proposal-title">Propuesta de la IA <span className="optional">— revísala antes de aceptarla</span></p>
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
            Descartar
          </button>
        </div>
      )}
    </div>
  );
}

import { Link, useParams } from "react-router-dom";
import { errorMessage } from "../api/client";
import { useAnalysis, useDocument, useRules } from "../api/hooks";
import { PdfReview } from "../components/PdfReview";

export function ReviewPage() {
  const { id } = useParams();
  const analysis = useAnalysis(id);
  const doc = useDocument(analysis.data?.contract_document_id);
  const rules = useRules();

  const err = analysis.error ?? doc.error ?? rules.error;
  return (
    <div className="card">
      <div className="card-header-row">
        <h2>Revisión visual de hallazgos</h2>
        <Link className="btn btn-secondary" to={`/analisis/${id}`}>
          ← Volver al análisis
        </Link>
      </div>
      {err ? (
        <p className="form-msg error">{errorMessage(err)}</p>
      ) : analysis.data && doc.data && rules.data ? (
        <PdfReview analysis={analysis.data} document={doc.data} rules={rules.data} />
      ) : (
        <p className="hint">Cargando…</p>
      )}
    </div>
  );
}

import { useRef, useState, type FormEvent } from "react";
import { RefreshCw, Trash2, Upload } from "lucide-react";
import { errorMessage } from "../api/client";
import { useDeleteDocument, useDocuments, useUploadDocument } from "../api/hooks";
import { DOC_TYPE_LABELS, EXTRACTION_LABELS, type DocType } from "../api/types";
import { ProgressBar } from "../components/ProgressBar";

export function DocumentsPage() {
  const docs = useDocuments();
  const upload = useUploadDocument();
  const remove = useDeleteDocument();
  const [docType, setDocType] = useState<DocType>("contrato");
  const [title, setTitle] = useState("");
  const [jurisdiction, setJurisdiction] = useState("EC");
  const [file, setFile] = useState<File | null>(null);
  const [filter, setFilter] = useState<"" | DocType>("");
  const [msg, setMsg] = useState<{ text: string; kind: "" | "error" | "success" }>({ text: "", kind: "" });
  // Avance del envío (0–1); al llegar a 1 el servidor todavía lee el PDF, sin avance medible.
  const [sent, setSent] = useState<number | null>(null);
  // Se guarda el formulario en un ref: tras un `await`, `e.currentTarget` ya es null.
  const formRef = useRef<HTMLFormElement>(null);

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!file) return setMsg({ text: "Selecciona un PDF.", kind: "error" });
    setMsg({ text: "", kind: "" });
    setSent(0);
    try {
      const d = await upload.mutateAsync({
        docType,
        title: title.trim(),
        jurisdiction: jurisdiction.trim() || "EC",
        file,
        onProgress: setSent,
      });
      setMsg({ text: `Listo: «${d.title ?? d.original_filename}» (${d.page_count} páginas).`, kind: "success" });
      setTitle("");
      setFile(null);
      formRef.current?.reset();
    } catch (err) {
      setMsg({ text: errorMessage(err), kind: "error" });
    } finally {
      setSent(null);
    }
  };

  const rows = (docs.data ?? []).filter((d) => !filter || d.doc_type === filter);

  return (
    <div className="grid-2">
      <div className="card">
        <h2>Subir documento</h2>
        <form ref={formRef} onSubmit={submit}>
          <label>
            Tipo
            <select value={docType} onChange={(e) => setDocType(e.target.value as DocType)}>
              <option value="contrato">Contrato</option>
              <option value="normativa">Normativa</option>
            </select>
          </label>
          <label>
            Título
            <input type="text" maxLength={200} placeholder="Ej. Contrato de servicios cloud" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label>
            País (código)
            <input type="text" maxLength={10} value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} />
          </label>
          <label>
            Archivo PDF
            <input type="file" accept="application/pdf" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button type="submit" className="btn btn-primary" disabled={upload.isPending}>
            {upload.isPending ? "Subiendo…" : <><Upload size={16} /> Subir</>}
          </button>
          {sent !== null && (
            <div className="upload-progress">
              <ProgressBar value={sent < 1 ? sent : undefined} label="Avance de la subida" />
              <p className="hint" role="status" aria-live="polite">
                {sent < 1 ? `Enviando el archivo… ${Math.round(sent * 100)} %` : "Leyendo el texto del PDF… puede tardar si tiene muchas páginas."}
              </p>
            </div>
          )}
          <p className={"form-msg " + msg.kind} role="status">
            {msg.text}
          </p>
        </form>
      </div>

      <div className="card">
        <h2>Documentos cargados</h2>
        <div className="filter-row">
          <label>
            Filtrar por tipo
            <select value={filter} onChange={(e) => setFilter(e.target.value as "" | DocType)}>
              <option value="">Todos</option>
              <option value="contrato">Contrato</option>
              <option value="normativa">Normativa</option>
            </select>
          </label>
          <button type="button" className="btn btn-secondary" onClick={() => docs.refetch()}>
            <RefreshCw size={16} /> Actualizar
          </button>
        </div>
        {docs.error && <p className="form-msg error" role="alert">{errorMessage(docs.error)}</p>}
        {docs.data && rows.length === 0 && (
          <p className="empty">Todavía no hay documentos. Sube un contrato con el formulario de la izquierda para empezar.</p>
        )}
        <table className="data-table">
          <thead>
            <tr>
              <th>Título</th>
              <th>Tipo</th>
              <th>País</th>
              <th>Páginas</th>
              <th>Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id}>
                <td>{d.title ?? d.original_filename}</td>
                <td>{DOC_TYPE_LABELS[d.doc_type]}</td>
                <td>{d.jurisdiction}</td>
                <td>{d.page_count}</td>
                <td>{EXTRACTION_LABELS[d.extraction_status] ?? d.extraction_status}</td>
                <td>
                  <button
                    type="button"
                    className="btn btn-icon btn-icon-danger"
                    title="Eliminar documento"
                    aria-label={`Eliminar «${d.title ?? d.original_filename}»`}
                    onClick={() => {
                      if (!confirm(`¿Eliminar «${d.title ?? d.original_filename}»?`)) return;
                      remove.mutate(d.id, { onError: (err) => setMsg({ text: errorMessage(err), kind: "error" }) });
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

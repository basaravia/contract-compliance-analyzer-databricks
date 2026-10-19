import { useState, type FormEvent } from "react";
import { errorMessage } from "../api/client";
import { useDeleteDocument, useDocuments, useUploadDocument } from "../api/hooks";
import type { DocType } from "../api/types";

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

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!file) return setMsg({ text: "Selecciona un PDF.", kind: "error" });
    setMsg({ text: "Subiendo y extrayendo texto…", kind: "" });
    try {
      const d = await upload.mutateAsync({ docType, title: title.trim(), jurisdiction: jurisdiction.trim() || "EC", file });
      setMsg({ text: `Documento subido (${d.page_count} páginas).`, kind: "success" });
      setTitle("");
      setFile(null);
      e.currentTarget.reset();
    } catch (err) {
      setMsg({ text: errorMessage(err), kind: "error" });
    }
  };

  const rows = (docs.data ?? []).filter((d) => !filter || d.doc_type === filter);

  return (
    <div className="grid-2">
      <div className="card">
        <h2>Subir documento</h2>
        <form onSubmit={submit}>
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
            Jurisdicción
            <input type="text" maxLength={10} value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} />
          </label>
          <label>
            Archivo PDF
            <input type="file" accept="application/pdf" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button type="submit" className="btn btn-primary" disabled={upload.isPending}>
            Subir
          </button>
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
            Actualizar
          </button>
        </div>
        {docs.error && <p className="form-msg error">{errorMessage(docs.error)}</p>}
        <table className="data-table">
          <thead>
            <tr>
              <th>Título</th>
              <th>Tipo</th>
              <th>Jurisd.</th>
              <th>Pág.</th>
              <th>Estado extracción</th>
              <th>Escaneado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id}>
                <td>{d.title ?? d.original_filename}</td>
                <td>{d.doc_type}</td>
                <td>{d.jurisdiction}</td>
                <td>{d.page_count}</td>
                <td>{d.extraction_status}</td>
                <td>{d.is_scanned ? "Sí" : "No"}</td>
                <td>
                  <button
                    type="button"
                    className="btn btn-danger btn-small"
                    onClick={() => {
                      if (!confirm(`¿Eliminar «${d.title ?? d.original_filename}»?`)) return;
                      remove.mutate(d.id, { onError: (err) => alert(errorMessage(err)) });
                    }}
                  >
                    Eliminar
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

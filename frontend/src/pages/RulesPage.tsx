import { useState, type FormEvent } from "react";
import { ApiError, errorMessage } from "../api/client";
import { useCreateRule, useDeleteRule, useImportRules, useRules, useUpdateRule } from "../api/hooks";
import type { Rule, Severity } from "../api/types";
import { ReferenceFields, toRefInput, type RefDraft } from "../components/ReferenceFields";
import { RuleEditorDialog } from "../components/RuleEditorDialog";

const EXAMPLE = `Regla: Cláusula de protección de datos personales
Descripción: El contrato debe incluir una cláusula de tratamiento de datos.
Categoría: proteccion_datos
Severidad: alta
Referencia: LOPDP Art. 5
---
Regla: Plazo de notificación de incidentes
Descripción: El contrato debe fijar un plazo máximo de notificación.
Severidad: alta
Referencia: LOPDP Art. 44`;

type Msg = { text: string; kind: "" | "error" | "success" };

function NewRuleForm() {
  const create = useCreateRule();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState<Severity>("media");
  const [jurisdiction, setJurisdiction] = useState("EC");
  const [refs, setRefs] = useState<RefDraft[]>([]);
  const [msg, setMsg] = useState<Msg>({ text: "", kind: "" });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await create.mutateAsync({
        name: name.trim(),
        description: description.trim(),
        category: category.trim() || null,
        severity,
        jurisdiction: jurisdiction.trim() || "EC",
        references: toRefInput(refs),
      });
      setMsg({ text: "Regla creada.", kind: "success" });
      setName("");
      setDescription("");
      setCategory("");
      setRefs([]);
    } catch (err) {
      setMsg({ text: errorMessage(err), kind: "error" });
    }
  };

  return (
    <div className="card">
      <h2>Nueva regla</h2>
      <form onSubmit={submit}>
        <label>
          Nombre
          <input type="text" maxLength={200} required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Descripción
          <textarea maxLength={5000} rows={3} required value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <div className="form-row">
          <label>
            Categoría
            <input type="text" maxLength={100} value={category} onChange={(e) => setCategory(e.target.value)} />
          </label>
          <label>
            Severidad
            <select value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
              <option value="alta">Alta</option>
              <option value="media">Media</option>
              <option value="baja">Baja</option>
            </select>
          </label>
          <label>
            Jurisdicción
            <input type="text" maxLength={10} value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} />
          </label>
        </div>
        <ReferenceFields value={refs} onChange={setRefs} />
        <button type="submit" className="btn btn-primary" disabled={create.isPending}>
          Crear regla
        </button>
        <p className={"form-msg " + msg.kind} role="status">
          {msg.text}
        </p>
      </form>
    </div>
  );
}

function ImportCard() {
  const imp = useImportRules();
  const [text, setText] = useState("");
  const [textMsg, setTextMsg] = useState<Msg>({ text: "", kind: "" });
  const [formatErrors, setFormatErrors] = useState<{ bloque: number | string; error: string }[]>([]);
  const [jsonMsg, setJsonMsg] = useState<Msg>({ text: "", kind: "" });
  const [jsonFile, setJsonFile] = useState<File | null>(null);

  const importText = async (e: FormEvent) => {
    e.preventDefault();
    setFormatErrors([]);
    try {
      await imp.mutateAsync({ kind: "text", text });
      setTextMsg({ text: "Reglas importadas correctamente.", kind: "success" });
      setText("");
    } catch (err) {
      setTextMsg({ text: errorMessage(err), kind: "error" });
      if (err instanceof ApiError) setFormatErrors(err.errors);
    }
  };

  const importJson = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!jsonFile) return setJsonMsg({ text: "Selecciona un archivo JSON.", kind: "error" });
    let parsed: unknown;
    try {
      parsed = JSON.parse(await jsonFile.text());
    } catch {
      return setJsonMsg({ text: "El archivo no contiene JSON válido.", kind: "error" });
    }
    try {
      await imp.mutateAsync({ kind: "json", payload: Array.isArray(parsed) ? { rules: parsed } : parsed });
      setJsonMsg({ text: "Reglas importadas correctamente.", kind: "success" });
      setJsonFile(null);
      e.currentTarget.reset();
    } catch (err) {
      setJsonMsg({ text: errorMessage(err), kind: "error" });
    }
  };

  return (
    <div className="card">
      <h2>Importación masiva de reglas</h2>
      <p className="hint">
        Sirve para cargar varias reglas nuevas de una vez. <strong>No es el editor de una regla existente</strong>: para modificarla
        usa «Editar» en la tabla de reglas.
      </p>
      <p className="hint">
        Formato: bloques separados por una línea <code>---</code>, con campos <code>Regla:</code>, <code>Descripción:</code>,{" "}
        <code>Categoría:</code>, <code>Severidad:</code> (alta|media|baja), <code>Jurisdicción:</code> y una o más líneas{" "}
        <code>Referencia:</code>.
      </p>
      <pre className="example-block">{EXAMPLE}</pre>
      <form onSubmit={importText}>
        <textarea rows={10} placeholder="Pega aquí el texto con el formato de arriba…" aria-label="Texto de reglas" value={text} onChange={(e) => setText(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={imp.isPending || !text.trim()}>
          Importar texto
        </button>
        <p className={"form-msg " + textMsg.kind} role="status">
          {textMsg.text}
        </p>
        <ul className="error-list">
          {formatErrors.map((x, i) => (
            <li key={i}>
              Bloque {x.bloque}: {x.error}
            </li>
          ))}
        </ul>
      </form>
      <h3>Importar JSON</h3>
      <form onSubmit={importJson}>
        <input type="file" accept="application/json" aria-label="Archivo JSON" onChange={(e) => setJsonFile(e.target.files?.[0] ?? null)} />
        <button type="submit" className="btn btn-secondary">
          Importar JSON
        </button>
        <p className={"form-msg " + jsonMsg.kind} role="status">
          {jsonMsg.text}
        </p>
      </form>
    </div>
  );
}

export function RulesPage() {
  const rules = useRules();
  const update = useUpdateRule();
  const remove = useDeleteRule();
  const [activeOnly, setActiveOnly] = useState(false);
  const [editing, setEditing] = useState<Rule | null>(null);
  const rows = (rules.data ?? []).filter((r) => !activeOnly || r.active);

  return (
    <>
      <div className="grid-2">
        <NewRuleForm />
        <ImportCard />
      </div>
      <div className="card">
        <h2>Reglas existentes</h2>
        <label className="inline-check">
          <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} /> Mostrar solo activas
        </label>
        {rules.error && <p className="form-msg error">{errorMessage(rules.error)}</p>}
        <table className="data-table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Categoría</th>
              <th>Severidad</th>
              <th>Jurisd.</th>
              <th>Estado</th>
              <th>Referencias</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>{r.category ?? "—"}</td>
                <td>{r.severity}</td>
                <td>{r.jurisdiction}</td>
                <td>
                  <div className="active-switch-wrap">
                    <button
                      type="button"
                      className="switch"
                      role="switch"
                      aria-checked={r.active}
                      aria-label={`Activar o desactivar «${r.name}»`}
                      onClick={() => update.mutate({ id: r.id, patch: { active: !r.active } }, { onError: (err) => alert(errorMessage(err)) })}
                    >
                      <span className="switch-track">
                        <span className="switch-thumb" />
                      </span>
                    </button>
                    <span className="switch-label">{r.active ? "Activa" : "Inactiva"}</span>
                  </div>
                </td>
                <td>{r.references.map((x) => x.citation + (x.page ? ` (p. ${x.page})` : "")).join("; ") || "—"}</td>
                <td>
                  <button type="button" className="btn btn-secondary btn-small" onClick={() => setEditing(r)}>
                    Editar
                  </button>{" "}
                  <button
                    type="button"
                    className="btn btn-danger btn-small"
                    onClick={() => confirm(`¿Eliminar la regla «${r.name}»?`) && remove.mutate(r.id, { onError: (err) => alert(errorMessage(err)) })}
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && <RuleEditorDialog key={editing.id} rule={editing} onClose={() => setEditing(null)} />}
    </>
  );
}

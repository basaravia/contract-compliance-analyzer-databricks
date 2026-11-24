import { useState, type FormEvent } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { errorMessage } from "../api/client";
import { useCreateRule, useDeleteRule, useRules, useUpdateRule } from "../api/hooks";
import { SEVERITY_LABELS, type Rule, type Severity } from "../api/types";
import { ReferenceFields, toRefInput, type RefDraft } from "../components/ReferenceFields";
import { RuleEditorDialog } from "../components/RuleEditorDialog";
import { RuleImportWizard } from "../components/RuleImportWizard";

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
      setMsg({ text: "Criterio creado.", kind: "success" });
      setName("");
      setDescription("");
      setCategory("");
      setRefs([]);
    } catch (err) {
      setMsg({ text: errorMessage(err), kind: "error" });
    }
  };

  return (
    <details className="card disclosure">
      <summary>
        <Plus size={16} /> Crear un criterio a mano
      </summary>
      <form onSubmit={submit}>
        <label>
          Nombre del criterio
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
            Importancia
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
          {create.isPending ? "Guardando…" : <><Plus size={16} /> Crear criterio</>}
        </button>
        <p className={"form-msg " + msg.kind} role="status">
          {msg.text}
        </p>
      </form>
    </details>
  );
}

export function RulesPage() {
  const rules = useRules();
  const update = useUpdateRule();
  const remove = useDeleteRule();
  const [activeOnly, setActiveOnly] = useState(false);
  const [editing, setEditing] = useState<Rule | null>(null);
  const [rowError, setRowError] = useState("");
  const rows = (rules.data ?? []).filter((r) => !activeOnly || r.active);

  return (
    <>
      <div className="grid-2">
        <RuleImportWizard />
        <NewRuleForm />
      </div>
      <div className="card">
        <h2>Criterios existentes</h2>
        <label className="inline-check">
          <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} /> Mostrar solo activas
        </label>
        {rules.error && <p className="form-msg error" role="alert">{errorMessage(rules.error)}</p>}
        {rowError && <p className="form-msg error" role="alert">{rowError}</p>}
        <table className="data-table">
          <thead>
            <tr>
              <th>Criterio</th>
              <th>Categoría</th>
              <th>Importancia</th>
              <th>País</th>
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
                <td>{SEVERITY_LABELS[r.severity] ?? r.severity}</td>
                <td>{r.jurisdiction}</td>
                <td>
                  <div className="active-switch-wrap">
                    <button
                      type="button"
                      className="switch"
                      role="switch"
                      aria-checked={r.active}
                      aria-label={`Activar o desactivar «${r.name}»`}
                      onClick={() => update.mutate({ id: r.id, patch: { active: !r.active } }, { onError: (err) => setRowError(errorMessage(err)) })}
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
                  <button type="button" className="btn btn-icon" title="Editar criterio" aria-label={`Editar «${r.name}»`} onClick={() => setEditing(r)}>
                    <Pencil size={16} />
                  </button>
                  <button
                    type="button"
                    className="btn btn-icon btn-icon-danger"
                    title="Eliminar criterio"
                    aria-label={`Eliminar «${r.name}»`}
                    onClick={() => confirm(`¿Eliminar el criterio «${r.name}»?`) && remove.mutate(r.id, { onError: (err) => setRowError(errorMessage(err)) })}
                  >
                    <Trash2 size={16} />
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

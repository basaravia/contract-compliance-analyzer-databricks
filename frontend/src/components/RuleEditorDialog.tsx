import { useState } from "react";
import { errorMessage } from "../api/client";
import { useUpdateRule } from "../api/hooks";
import type { Rule, Severity } from "../api/types";
import { ReferenceFields, toRefInput, type RefDraft } from "./ReferenceFields";

interface Draft {
  name: string;
  description: string;
  category: string;
  severity: Severity;
  active: boolean;
  references: RefDraft[];
}

const fromRule = (r: Rule): Draft => ({
  name: r.name,
  description: r.description,
  category: r.category ?? "",
  severity: r.severity,
  active: r.active,
  references: r.references.map((x) => ({ citation: x.citation, page: x.page ? String(x.page) : "" })),
});

const toPayload = (d: Draft) => ({
  name: d.name.trim(),
  description: d.description.trim(),
  category: d.category.trim() || null,
  severity: d.severity,
  active: d.active,
  references: toRefInput(d.references),
});

/** Editor de una regla existente, con las dos vistas del editor clásico: formulario y JSON (el mismo objeto). */
export function RuleEditorDialog({ rule, onClose }: { rule: Rule; onClose: () => void }) {
  const update = useUpdateRule();
  const [tab, setTab] = useState<"form" | "json">("form");
  const [draft, setDraft] = useState<Draft>(() => fromRule(rule));
  const [json, setJson] = useState(() => JSON.stringify(toPayload(fromRule(rule)), null, 2));
  const [jsonError, setJsonError] = useState("");
  const [msg, setMsg] = useState("");

  const patch = (p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p }));

  const switchTab = (next: "form" | "json") => {
    if (next === "json") {
      setJson(JSON.stringify(toPayload(draft), null, 2));
      setJsonError("");
    } else {
      // Al volver al formulario se aplica el JSON si es válido; si no, se queda donde estaba.
      try {
        const o = JSON.parse(json);
        setDraft({
          name: String(o.name ?? ""),
          description: String(o.description ?? ""),
          category: o.category ?? "",
          severity: (["alta", "media", "baja"].includes(o.severity) ? o.severity : "media") as Severity,
          active: o.active !== false,
          references: (Array.isArray(o.references) ? o.references : []).map((x: { citation?: string; page?: number | null }) => ({
            citation: String(x.citation ?? ""),
            page: x.page ? String(x.page) : "",
          })),
        });
      } catch {
        setJsonError("JSON inválido: corrígelo antes de volver al formulario.");
        return;
      }
    }
    setTab(next);
  };

  const save = async () => {
    let payload = toPayload(draft);
    if (tab === "json") {
      try {
        const o = JSON.parse(json);
        // id, jurisdiction, created_*/updated_* son informativos: no se envían.
        payload = {
          name: o.name,
          description: o.description,
          category: o.category ?? null,
          severity: o.severity,
          active: o.active,
          references: (o.references ?? []).map((x: { citation: string; page?: number | null }) => ({ citation: x.citation, page: x.page ?? null })),
        };
      } catch {
        setJsonError("JSON inválido.");
        return;
      }
    }
    try {
      await update.mutateAsync({ id: rule.id, patch: payload });
      onClose();
    } catch (err) {
      setMsg(errorMessage(err));
    }
  };

  return (
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="rule-editor-title">
        <div className="modal-header">
          <h2 id="rule-editor-title">Editar regla</h2>
          <button type="button" className="modal-close" aria-label="Cerrar editor" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-tabs" role="tablist" aria-label="Modo de edición de la regla">
          {(["form", "json"] as const).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              className={"modal-tab-btn" + (tab === t ? " active" : "")}
              onClick={() => switchTab(t)}
            >
              {t === "form" ? "Formulario" : "JSON"}
            </button>
          ))}
        </div>
        <div className="modal-body">
          {tab === "form" ? (
            <form onSubmit={(e) => e.preventDefault()}>
              <label>
                Nombre
                <input type="text" maxLength={200} required value={draft.name} onChange={(e) => patch({ name: e.target.value })} />
              </label>
              <label>
                Descripción
                <textarea maxLength={5000} rows={3} required value={draft.description} onChange={(e) => patch({ description: e.target.value })} />
              </label>
              <div className="form-row">
                <label>
                  Categoría
                  <input type="text" maxLength={100} value={draft.category} onChange={(e) => patch({ category: e.target.value })} />
                </label>
                <label>
                  Severidad
                  <select value={draft.severity} onChange={(e) => patch({ severity: e.target.value as Severity })}>
                    <option value="alta">Alta</option>
                    <option value="media">Media</option>
                    <option value="baja">Baja</option>
                  </select>
                </label>
                <label>
                  Jurisdicción
                  <input type="text" value={rule.jurisdiction} disabled />
                </label>
              </div>
              <p className="hint">La jurisdicción se fija al crear la regla y no puede modificarse desde este editor.</p>
              <ReferenceFields value={draft.references} onChange={(references) => patch({ references })} />
              <div className="switch-field">
                <button
                  type="button"
                  className="switch"
                  role="switch"
                  aria-checked={draft.active}
                  aria-label="Regla activa"
                  onClick={() => patch({ active: !draft.active })}
                >
                  <span className="switch-track">
                    <span className="switch-thumb" />
                  </span>
                </button>
                <span className="switch-label">{draft.active ? "Activa" : "Inactiva"}</span>
              </div>
            </form>
          ) : (
            <>
              <textarea
                className={"json-editor" + (jsonError ? " invalid" : "")}
                spellCheck={false}
                rows={18}
                aria-label="Regla en JSON"
                value={json}
                onChange={(e) => {
                  setJson(e.target.value);
                  setJsonError("");
                }}
              />
              <p className="hint">
                Es el mismo objeto que el formulario. <code>id</code>, <code>jurisdiction</code>, <code>created_by</code>,{" "}
                <code>created_at</code> y <code>updated_at</code> son informativos y no se envían al guardar.
              </p>
              <p className="form-msg error" role="alert">
                {jsonError}
              </p>
            </>
          )}
        </div>
        <div className="modal-footer">
          <p className="form-msg error" role="status">
            {msg}
          </p>
          <div className="modal-footer-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancelar
            </button>
            <button type="button" className="btn btn-primary" onClick={save} disabled={update.isPending}>
              Guardar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

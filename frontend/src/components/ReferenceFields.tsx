export interface RefDraft {
  citation: string;
  page: string;
}

export function toRefInput(refs: RefDraft[]) {
  return refs
    .filter((r) => r.citation.trim())
    .map((r) => ({ citation: r.citation.trim(), page: r.page ? Number(r.page) : null }));
}

export function ReferenceFields({ value, onChange }: { value: RefDraft[]; onChange: (v: RefDraft[]) => void }) {
  const set = (i: number, patch: Partial<RefDraft>) => onChange(value.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <fieldset>
      <legend>Referencias normativas</legend>
      {value.map((r, i) => (
        <div className="reference-row" key={i}>
          <input
            type="text"
            className="ref-citation"
            placeholder="Cita, ej. LOPDP Art. 5"
            maxLength={300}
            aria-label={`Cita ${i + 1}`}
            value={r.citation}
            onChange={(e) => set(i, { citation: e.target.value })}
          />
          <input
            type="number"
            className="ref-page"
            placeholder="Pág."
            min={1}
            aria-label={`Página ${i + 1}`}
            value={r.page}
            onChange={(e) => set(i, { page: e.target.value })}
          />
          <button type="button" className="btn btn-secondary btn-small" onClick={() => onChange(value.filter((_, j) => j !== i))}>
            Quitar
          </button>
        </div>
      ))}
      <button type="button" className="btn btn-secondary btn-small" onClick={() => onChange([...value, { citation: "", page: "" }])}>
        + Añadir referencia
      </button>
    </fieldset>
  );
}

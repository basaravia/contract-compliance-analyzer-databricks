/** Barra de avance accesible. Sin `value` es indeterminada (se sabe que trabaja, no cuánto falta). */
export function ProgressBar({ value, label }: { value?: number; label: string }) {
  const pct = value === undefined ? undefined : Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className="progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
      <div className={"progress-fill" + (pct === undefined ? " indeterminate" : "")} style={pct === undefined ? undefined : { width: `${pct}%` }} />
    </div>
  );
}

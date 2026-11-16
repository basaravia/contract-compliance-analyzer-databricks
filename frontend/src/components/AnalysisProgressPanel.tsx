import { useEffect, useRef, useState } from "react";
import type { AnalysisProgress } from "../api/types";
import { ProgressBar } from "./ProgressBar";

type Live = NonNullable<AnalysisProgress["live"]>;

export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} min ${s % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

/** Avance global 0–1: las fases cortas pesan poco y la evaluación de criterios ocupa casi toda la barra. */
function overall(l: Live): number {
  if (l.phase === 0) return 0.03;
  if (l.phase === 1) return 0.08;
  if (l.phase === 2) return 0.1 + 0.85 * (l.total ? l.done / l.total : 0);
  return 0.97;
}

/** Hora del servidor interpolada con el reloj local entre sondeos: no depende de que el equipo tenga bien la hora. */
function useServerClock(nowTs: number): number {
  const ref = useRef({ server: nowTs, local: performance.now() });
  if (nowTs !== ref.current.server) ref.current = { server: nowTs, local: performance.now() };
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return ref.current.server + (performance.now() - ref.current.local) / 1000;
}

/** Estimación con rango (±35 %), solo después de evaluar al menos un criterio. */
function remaining(l: Live, elapsed: number): string | null {
  if (l.phase !== 2 || l.done <= 0 || l.done >= l.total) return null;
  const rest = ((l.total - l.done) * elapsed) / l.done;
  return `entre ${duration(rest * 0.65)} y ${duration(rest * 1.35)}`;
}

export function AnalysisProgressPanel({ live }: { live: Live }) {
  const now = useServerClock(live.now_ts);
  const elapsed = now - live.started_ts;
  const quiet = now - live.updated_ts;
  const left = remaining(live, elapsed);
  const current =
    live.phase === 2
      ? `Evaluando criterio ${Math.min(live.done + 1, live.total)} de ${live.total}`
      : live.phases[live.phase];

  return (
    <div className="analysis-progress">
      <ol className="steps" aria-label="Etapas del análisis">
        {live.phases.map((name, i) => (
          <li key={name} className={i < live.phase ? "done" : i === live.phase ? "current" : ""} aria-current={i === live.phase ? "step" : undefined}>
            {name}
          </li>
        ))}
      </ol>
      <ProgressBar value={overall(live)} label="Avance del análisis" />
      <p className="progress-now" role="status" aria-live="polite">
        <strong>{current}</strong>
        {live.detail && <> · {live.detail}</>}
      </p>
      <p className="hint">
        Tiempo transcurrido: {duration(elapsed)}
        {left && <> · Falta aproximadamente {left}</>}
        {quiet > 40 && <> · Sigue trabajando: algunos criterios tardan más que otros.</>}
      </p>
      <p className="hint">Puedes salir de esta página: el análisis continúa y lo encontrarás en «Análisis existentes».</p>
    </div>
  );
}

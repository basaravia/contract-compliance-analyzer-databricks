"""Progreso en vivo de los análisis, en memoria del proceso (la app corre con un solo worker).

El navegador lo consulta cada pocos segundos (`GET /api/analyses/{id}/progress`): sondeo simple en lugar de SSE o
WebSocket, que es lo que mejor atraviesa el proxy de Databricks Apps (misma técnica que el comparador normativo).
Si el proceso se reinicia, el progreso se pierde y el análisis queda marcado como interrumpido."""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field

# Fases en el lenguaje del auditor, en el orden en que ocurren.
PHASES = ("Leyendo el contrato", "Preparando la búsqueda", "Evaluando criterios", "Guardando resultados")


@dataclass
class Progress:
    phase: int = 0
    done: int = 0       # criterios evaluados
    total: int = 0      # criterios a evaluar
    detail: str = ""    # qué se está haciendo ahora, p. ej. el nombre del criterio
    started_ts: float = field(default_factory=time.time)
    updated_ts: float = field(default_factory=time.time)


_lock = threading.Lock()
_running: dict[str, Progress] = {}


def start(analysis_id: str, total: int) -> None:
    with _lock:
        _running[analysis_id] = Progress(total=total)


def report(analysis_id: str, *, phase: int | None = None, done: int | None = None, detail: str | None = None) -> None:
    with _lock:
        p = _running.get(analysis_id)
        if p is None:
            return
        if phase is not None:
            p.phase = phase
        if done is not None:
            p.done = done
        if detail is not None:
            p.detail = detail
        p.updated_ts = time.time()


def finish(analysis_id: str) -> None:
    with _lock:
        _running.pop(analysis_id, None)


def snapshot(analysis_id: str) -> dict | None:
    """Copia del progreso con la hora del servidor (`now_ts`), para que el navegador calcule tiempos sin depender
    de su propio reloj. `None` si el análisis no está en curso en este proceso."""
    with _lock:
        p = _running.get(analysis_id)
        data = asdict(p) if p else None
    if data is None:
        return None
    return {**data, "phases": list(PHASES), "now_ts": time.time()}

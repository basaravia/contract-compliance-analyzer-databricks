"""Implementación de VectorIndex con FAISS (índice plano, similitud coseno
vía producto interno sobre vectores normalizados).

Índice en memoria, reconstruido por análisis (escala adecuada para el MVP:
un contrato tiene decenas/cientos de fragmentos, no millones). Para producción
a mayor escala, sustituir por `PgVectorIndex` o `VertexVectorSearchIndex`
implementando la misma interfaz `VectorIndex`.
"""
from __future__ import annotations

import faiss
import numpy as np

from app.retrieval.base import SearchResult, VectorIndex


class FaissVectorIndex(VectorIndex):
    def __init__(self, dim: int):
        self.dim = dim
        self._index = faiss.IndexFlatIP(dim)
        self._chunk_ids: list[str] = []

    def build(self, chunk_ids: list[str], vectors: np.ndarray) -> None:
        if vectors.shape[0] != len(chunk_ids):
            raise ValueError("chunk_ids y vectors deben tener la misma longitud")
        self._index = faiss.IndexFlatIP(self.dim)
        if vectors.shape[0] > 0:
            self._index.add(np.ascontiguousarray(vectors.astype("float32")))
        self._chunk_ids = list(chunk_ids)

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        if self._index.ntotal == 0:
            return []
        q = np.ascontiguousarray(query_vector.reshape(1, -1).astype("float32"))
        top_k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(q, top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            results.append(SearchResult(chunk_id=self._chunk_ids[idx], score=float(score)))
        return results

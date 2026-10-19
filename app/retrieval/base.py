"""Interfaz de índice vectorial. Permite sustituir FAISS por pgvector o
Vertex AI Vector Search sin tocar el resto de la aplicación: cualquier
implementación futura solo necesita cumplir `VectorIndex`."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class SearchResult:
    chunk_id: str
    score: float


class VectorIndex(ABC):
    @abstractmethod
    def build(self, chunk_ids: list[str], vectors: np.ndarray) -> None:
        """Construye (o reconstruye) el índice a partir de vectores ya normalizados."""
        raise NotImplementedError

    @abstractmethod
    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        raise NotImplementedError

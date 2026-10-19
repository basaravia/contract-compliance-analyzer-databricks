"""Adaptador de embeddings, con proveedor Vertex AI (gemini-embedding-001)
y fallback local/mock determinista para poder arrancar el MVP sin
credenciales de Google Cloud.

Selección por configuración: EMBEDDING_PROVIDER=mock|vertex.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import numpy as np

from app.config import settings

MOCK_EMBEDDING_DIM = 128


class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Devuelve un array (n_textos, dim) float32."""
        raise NotImplementedError


class MockEmbeddingProvider(EmbeddingProvider):
    """Embeddings deterministas basados en hashing de tokens (bag-of-hashed-words).

    No captura semántica real, pero es 100% determinista, no requiere
    credenciales ni descargas, y produce una recuperación por similitud
    razonable para coincidencias léxicas, suficiente para el MVP.
    """

    def __init__(self, dim: int = MOCK_EMBEDDING_DIM):
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dim), dtype="float32")
        for i, text in enumerate(texts):
            vectors[i] = self._embed_one(text)
        return vectors

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype="float32")
        tokens = _tokenize(text)
        if not tokens:
            return vec
        for token in tokens:
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h // self.dim) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec


def _tokenize(text: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(t) > 2]


class VertexEmbeddingProvider(EmbeddingProvider):
    """Adaptador real a Vertex AI (gemini-embedding-001) vía LangChain.

    Requiere `langchain-google-vertexai` + `google-cloud-aiplatform` instalados
    y credenciales válidas (GOOGLE_APPLICATION_CREDENTIALS / ADC). Si falla la
    inicialización, se debe usar `get_embedding_provider()` con
    EMBEDDING_PROVIDER=mock en su lugar.
    """

    def __init__(self, dim: int = 3072):
        self.dim = dim
        try:
            from langchain_google_vertexai import VertexAIEmbeddings
        except ImportError as e:
            raise RuntimeError(
                "langchain-google-vertexai no está instalado. "
                "Instálalo o usa EMBEDDING_PROVIDER=mock."
            ) from e

        self._client = VertexAIEmbeddings(
            model_name=settings.vertex_embedding_model,
            project=settings.google_cloud_project or None,
            location=settings.google_cloud_location,
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self._client.embed_documents(texts)
        arr = np.array(vectors, dtype="float32")
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms


def get_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_provider == "vertex":
        try:
            return VertexEmbeddingProvider()
        except Exception:
            # Fallback seguro: el MVP debe poder arrancar sin credenciales.
            return MockEmbeddingProvider()
    return MockEmbeddingProvider()

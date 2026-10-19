"""Adaptador de embeddings, con proveedor Vertex AI (gemini-embedding-001)
y fallback local/mock determinista para poder arrancar el MVP sin
credenciales de Google Cloud.

Selección por configuración: EMBEDDING_PROVIDER=mock|vertex|foundry.
"""
from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod

import httpx
import numpy as np

from app import foundry_config
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


class FoundryEmbeddingProvider(EmbeddingProvider):
    """Embeddings de Azure AI Foundry (p. ej. text-embedding-3-large, 3072 dimensiones).

    Mismas variables FOUNDRY_AI_* que el LLM más FOUNDRY_AI_EMBED_DEPLOYMENT. Sin respaldo silencioso a mock:
    si falta configuración o la llamada falla, el error es visible (un índice mock aparentaría semántica real)."""

    BATCH = 16
    RETRIES = 3

    def __init__(self):
        missing = foundry_config.missing(embeddings=True)
        if missing:
            raise RuntimeError(f"Faltan variables de configuración para embeddings de Foundry: {', '.join(missing)}")
        self.dim = settings.foundry_embed_dim
        self._client = httpx.Client(
            base_url=foundry_config.deployment_base_url(settings.foundry_ai_embed_deployment),
            params={"api-version": settings.foundry_ai_api_version},
            headers={"api-key": settings.foundry_ai_token},
            timeout=settings.foundry_timeout_s,
        )

    def _post(self, batch: list[str]) -> list[list[float]]:
        last: Exception | None = None
        for attempt in range(self.RETRIES):
            try:
                resp = self._client.post("/embeddings", json={"input": batch})
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("reintentable", request=resp.request, response=resp)
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
                return [d["embedding"] for d in data]
            except (httpx.HTTPError, KeyError, ValueError) as e:
                last = e
                time.sleep(min(2**attempt, 8))
        # Solo el tipo: el mensaje de httpx puede incluir URL o cabeceras.
        raise RuntimeError(f"Fallo al obtener embeddings de Foundry ({type(last).__name__})")

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH):
            vectors.extend(self._post([t if t.strip() else " " for t in texts[i : i + self.BATCH]]))
        arr = np.array(vectors, dtype="float32").reshape(len(texts), -1)
        if arr.shape[1] != self.dim:
            raise RuntimeError(
                f"El modelo devolvió {arr.shape[1]} dimensiones y se esperaban {self.dim} (FOUNDRY_EMBED_DIM)"
            )
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms


def get_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_provider == "foundry":
        return FoundryEmbeddingProvider()  # sin respaldo a mock: ver la clase
    if settings.embedding_provider == "vertex":
        try:
            return VertexEmbeddingProvider()
        except Exception:
            # Fallback seguro: el MVP debe poder arrancar sin credenciales.
            return MockEmbeddingProvider()
    return MockEmbeddingProvider()

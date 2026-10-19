"""Tests de la capa de recuperación: `MockEmbeddingProvider` y `FaissVectorIndex`.

Cubren determinismo y normalización de los embeddings mock, y que el índice
FAISS (detrás de la interfaz `VectorIndex`) devuelva el vecino más similar en
primer lugar, maneje índices vacíos y `top_k` mayor que el número de vectores
sin lanzar excepciones.
"""
from __future__ import annotations

import numpy as np

from app.retrieval.embeddings import MOCK_EMBEDDING_DIM, MockEmbeddingProvider
from app.retrieval.faiss_index import FaissVectorIndex


def test_mock_embedding_is_deterministic():
    provider = MockEmbeddingProvider()
    text = "El proveedor se compromete a proteger los datos personales conforme a la LOPDP."

    v1 = provider.embed([text])[0]
    v2 = provider.embed([text])[0]

    assert np.allclose(v1, v2)


def test_mock_embedding_nonzero_vectors_have_unit_norm():
    provider = MockEmbeddingProvider()
    vectors = provider.embed([
        "Clausula de proteccion de datos personales conforme a la LOPDP.",
        "Plazo maximo para notificar incidentes de seguridad.",
    ])

    for vec in vectors:
        norm = np.linalg.norm(vec)
        if norm > 0:
            assert abs(norm - 1.0) < 1e-5


def test_mock_embedding_distinct_texts_produce_distinct_vectors():
    provider = MockEmbeddingProvider()
    v1 = provider.embed(["Clausula de proteccion de datos personales."])[0]
    v2 = provider.embed(["Plazo de entrega de mercaderia en el puerto."])[0]

    assert not np.allclose(v1, v2)


def test_mock_embedding_empty_text_returns_zero_vector_without_exception():
    provider = MockEmbeddingProvider()
    vec = provider.embed([""])[0]
    assert vec.shape == (MOCK_EMBEDDING_DIM,)
    assert np.allclose(vec, np.zeros(MOCK_EMBEDDING_DIM, dtype="float32"))


def test_faiss_index_returns_most_similar_chunk_first():
    provider = MockEmbeddingProvider()
    texts = {
        "c1": "Clausula de proteccion de datos personales conforme a la LOPDP.",
        "c2": "Plazo maximo para notificar incidentes de seguridad.",
        "c3": "Condiciones de pago y facturacion mensual del contrato.",
    }
    chunk_ids = list(texts.keys())
    vectors = provider.embed(list(texts.values()))

    index = FaissVectorIndex(dim=provider.dim)
    index.build(chunk_ids, vectors)

    # Consulta idéntica a uno de los vectores indexados (c2)
    query = provider.embed([texts["c2"]])[0]
    results = index.search(query, top_k=2)

    assert len(results) == 2
    assert results[0].chunk_id == "c2"
    # La coincidencia exacta debe tener el score más alto (similitud coseno ~1.0)
    assert results[0].score >= results[1].score
    assert results[0].score > 0.99


def test_faiss_index_empty_search_returns_empty_list_without_exception():
    provider = MockEmbeddingProvider()
    index = FaissVectorIndex(dim=provider.dim)
    index.build([], np.zeros((0, provider.dim), dtype="float32"))

    query = provider.embed(["cualquier texto de consulta"])[0]
    results = index.search(query, top_k=5)

    assert results == []


def test_faiss_index_top_k_greater_than_available_does_not_break():
    provider = MockEmbeddingProvider()
    texts = ["Primer fragmento del contrato.", "Segundo fragmento del contrato."]
    vectors = provider.embed(texts)

    index = FaissVectorIndex(dim=provider.dim)
    index.build(["a", "b"], vectors)

    query = provider.embed([texts[0]])[0]
    results = index.search(query, top_k=50)

    assert len(results) == 2
    ids = {r.chunk_id for r in results}
    assert ids == {"a", "b"}

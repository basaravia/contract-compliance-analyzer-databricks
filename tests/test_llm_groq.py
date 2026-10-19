"""Evaluador Groq: se prueba contra un transporte httpx simulado (sin red ni clave real)."""
import json

import httpx

from app.config import settings
from app.llm.base import RetrievedChunk, RuleContext
from app.llm.groq_openai import GroqRuleEvaluator
from app.pdf.coords import BBoxPoints


def _evaluator(monkeypatch, handler):
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(settings, "groq_llm_model", "test-model")
    ev = GroqRuleEvaluator()
    ev._client = httpx.Client(
        base_url="http://groq.test/v1", headers=ev._client.headers, transport=httpx.MockTransport(handler)
    )
    return ev


RULE = RuleContext("Regla", "Descripción", "EC", ["LOPDP Art. 5"])
CHUNKS = [RetrievedChunk("c1", 1, "El proveedor tratará los datos conforme a la ley.", BBoxPoints(10, 10, 200, 40), 0.9)]


def _reply(payload):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})


def test_groq_ok(monkeypatch):
    seen = {}

    def handler(req):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return _reply({"status": "cumple", "justification": "ok", "evidence_text": "tratará los datos",
                       "page": 1, "bbox": {"x0": 10, "y0": 10, "x1": 200, "y1": 40}, "confidence": 0.8})

    r = _evaluator(monkeypatch, handler).evaluate(RULE, CHUNKS)
    assert r.status == "cumple" and r.page == 1
    assert seen["auth"] == "Bearer test-key" and seen["body"]["model"] == "test-model"


def test_groq_http_error_degrades(monkeypatch):
    r = _evaluator(monkeypatch, lambda req: httpx.Response(429)).evaluate(RULE, CHUNKS)
    assert r.status == "requiere_revision" and r.bbox is None


def test_groq_invalid_json_degrades(monkeypatch):
    r = _evaluator(monkeypatch, lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "no json"}}]})).evaluate(RULE, CHUNKS)
    assert r.status == "requiere_revision"


def test_groq_page_outside_chunks_drops_evidence(monkeypatch):
    h = lambda req: _reply({"status": "cumple", "justification": "x", "page": 9,
                            "bbox": {"x0": 1, "y0": 1, "x1": 2, "y1": 2}, "confidence": 0.9})
    r = _evaluator(monkeypatch, h).evaluate(RULE, CHUNKS)
    assert r.status == "requiere_revision" and r.bbox is None


def test_groq_without_key_falls_back_to_mock(monkeypatch):
    from app.llm import get_rule_evaluator
    from app.llm.mock import MockRuleEvaluator

    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "")
    assert isinstance(get_rule_evaluator(), MockRuleEvaluator)

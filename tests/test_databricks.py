"""Despliegue en Databricks Apps: identidad del proxy, SPA, Volume, Lakebase y Model Serving.

Nada de esto toca red ni un workspace real: el SDK se sustituye por dobles."""
from __future__ import annotations

import io
import json
import types

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.databricks_client as dbx_client
import app.main as main_module
from app import storage
from app.config import settings
from app.db import Base, get_db
from app.llm.base import RetrievedChunk, RuleContext
from app.llm.foundry import FoundryRuleEvaluator
from app.main import create_app, validate_runtime_config
from app.pdf.coords import BBoxPoints

IDENTITY = {"X-Forwarded-Email": "ana@example.com", "X-Forwarded-Preferred-Username": "ana@example.com"}


@pytest.fixture()
def dbx_client_app(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'dbx.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(settings, "auth_mode", "databricks")
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    application = create_app()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    application.dependency_overrides[get_db] = override_get_db
    c = TestClient(application, base_url="https://app.test", follow_redirects=False)
    yield c
    engine.dispose()


def test_api_without_proxy_identity_is_401(dbx_client_app):
    assert dbx_client_app.get("/api/rules").status_code == 401


def test_api_with_proxy_identity_is_ok_and_me_reports_it(dbx_client_app):
    assert dbx_client_app.get("/api/rules", headers=IDENTITY).status_code == 200
    me = dbx_client_app.get("/auth/me", headers=IDENTITY).json()
    assert me == {"email": "ana@example.com", "name": "ana@example.com", "auth_mode": "databricks"}


def test_writes_still_require_csrf(dbx_client_app):
    body = {"name": "R", "description": "D"}
    assert dbx_client_app.post("/api/rules", json=body, headers=IDENTITY).status_code == 403
    dbx_client_app.get("/healthz")  # entrega la cookie CSRF
    token = dbx_client_app.cookies.get("ccap_csrf")
    r = dbx_client_app.post("/api/rules", json=body, headers={**IDENTITY, "X-CSRF-Token": token})
    assert r.status_code == 201 and r.json()["created_by"] == "ana@example.com"


def test_login_page_redirects_home_because_the_platform_already_authenticated(dbx_client_app):
    r = dbx_client_app.get("/login")
    assert r.status_code == 302 and r.headers["location"] == "/"


def test_production_start_accepts_databricks_without_secret_key(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_mode", "databricks")
    monkeypatch.setattr(settings, "secret_key", main_module.DEFAULT_SECRET)
    validate_runtime_config()  # no lanza


def test_production_start_still_rejects_local_auth(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_mode", "local")
    with pytest.raises(RuntimeError):
        validate_runtime_config()


# --- SPA de React ---------------------------------------------------------------------------------
def test_spa_is_served_with_client_side_routes_but_api_404s_stay_404(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>spa</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(main_module, "FRONTEND_DIST", dist)
    monkeypatch.setattr(settings, "auth_mode", "databricks")
    c = TestClient(create_app(), follow_redirects=False)

    assert "<title>spa</title>" in c.get("/").text
    assert "<title>spa</title>" in c.get("/analisis/123").text  # ruta del cliente
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/api/no-existe", headers=IDENTITY).status_code == 404
    assert c.get("/../etc/passwd").status_code in (404, 200) and "root:" not in c.get("/../etc/passwd").text
    assert c.get("/healthz").json() == {"status": "ok"}


# --- Volume de Unity Catalog -----------------------------------------------------------------------
class FakeFiles:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload(self, path, contents, overwrite=False):
        self.objects[path] = contents.read()

    def download(self, path):
        if path not in self.objects:
            raise FileNotFoundError(path)
        return types.SimpleNamespace(contents=io.BytesIO(self.objects[path]))

    def delete(self, path):
        self.objects.pop(path, None)


@pytest.fixture()
def volume(monkeypatch):
    fake = types.SimpleNamespace(files=FakeFiles())
    monkeypatch.setattr(settings, "upload_volume_path", "/Volumes/cat/sch/vol/uploads/")
    monkeypatch.setattr(dbx_client, "_client", fake)
    return fake.files


def test_storage_roundtrip_restores_a_pdf_lost_with_the_container_disk(volume, tmp_path):
    local = tmp_path / "abc.pdf"
    local.write_bytes(b"%PDF-1.7 contenido")
    storage.push("abc.pdf", local)
    assert volume.objects["/Volumes/cat/sch/vol/uploads/abc.pdf"] == b"%PDF-1.7 contenido"

    local.unlink()  # el contenedor se reinició
    storage.ensure_local("abc.pdf", local)
    assert local.read_bytes() == b"%PDF-1.7 contenido"

    storage.remove("abc.pdf")
    assert volume.objects == {}


def test_storage_accepts_three_part_volume_name(monkeypatch):
    monkeypatch.setattr(settings, "upload_volume_path", "main.contratos.pdfs")
    assert storage._remote("a.pdf") == "/Volumes/main/contratos/pdfs/a.pdf"


def test_storage_rejects_names_with_path_separators(volume, tmp_path):
    with pytest.raises(ValueError):
        storage.push("../escape.pdf", tmp_path / "x")


def test_storage_is_a_noop_without_volume(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_volume_path", "")
    local = tmp_path / "a.pdf"
    storage.ensure_local("a.pdf", local)  # no descarga ni lanza
    assert not local.exists()


def test_storage_missing_in_volume_is_logged_not_raised(volume, tmp_path):
    storage.ensure_local("no-esta.pdf", tmp_path / "no-esta.pdf")
    assert not (tmp_path / "no-esta.pdf").exists()


# --- Lakebase ----------------------------------------------------------------------------------------
def test_lakebase_engine_uses_oauth_token_as_password(monkeypatch):
    import app.db as db_module

    for k, v in dict(pghost="inst.database.cloud.databricks.com", pguser="sp-uuid", pgdatabase="contratos").items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(dbx_client, "oauth_token", lambda: "tok-123")
    eng = db_module._build_engine()
    try:
        assert eng.url.drivername == "postgresql+psycopg"
        assert (eng.url.host, eng.url.username, eng.url.database) == ("inst.database.cloud.databricks.com", "sp-uuid", "contratos")
        assert eng.url.query["sslmode"] == "require" and eng.url.password is None  # nunca en la URL
        seen: dict = {}

        def fake_connect(*args, **kwargs):
            seen.update(kwargs)
            return object()

        monkeypatch.setattr(eng.dialect, "connect", fake_connect)
        eng.pool._creator(None)  # abre una conexión nueva: dispara el evento do_connect
        assert seen["password"] == "tok-123"
    finally:
        eng.dispose()


# --- Azure AI Foundry ----------------------------------------------------------------------------------
RULE = RuleContext("Regla", "Descripción", "EC", ["LOPDP Art. 5"])
CHUNKS = [RetrievedChunk("c1", 1, "El proveedor tratará los datos conforme a la ley.", BBoxPoints(10, 10, 200, 40), 0.9)]


def _foundry(monkeypatch, **over):
    vals = dict(foundry_ai_endpoint="https://rec.openai.azure.com/openai/v1/", foundry_ai_token="tok",
                foundry_ai_api_version="2024-10-21", foundry_ai_deployment="gpt-x", foundry_omit_temperature=False)
    vals.update(over)
    for k, v in vals.items():
        monkeypatch.setattr(settings, k, v)


def test_foundry_evaluator_calls_azure_deployment_with_api_key(monkeypatch):
    _foundry(monkeypatch, foundry_omit_temperature=True)
    ev = FoundryRuleEvaluator()
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers["api-key"], json.loads(req.content)
        content = {"status": "cumple", "justification": "ok", "evidence_text": "tratará los datos", "page": 1,
                   "bbox": {"x0": 10, "y0": 10, "x1": 200, "y1": 40}, "confidence": 0.8}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    ev._client = httpx.Client(base_url=ev._client.base_url, params=ev._client.params, headers=ev._client.headers,
                              transport=httpx.MockTransport(handler))
    assert ev.evaluate(RULE, CHUNKS).status == "cumple"
    assert seen["url"] == "https://rec.openai.azure.com/openai/deployments/gpt-x/chat/completions?api-version=2024-10-21"
    assert seen["key"] == "tok" and "temperature" not in seen["body"]


def test_foundry_evaluator_requires_config_and_rejects_placeholders(monkeypatch):
    _foundry(monkeypatch, foundry_ai_token="")
    with pytest.raises(RuntimeError, match="FOUNDRY_AI_TOKEN"):
        FoundryRuleEvaluator()
    _foundry(monkeypatch, foundry_ai_endpoint="REEMPLAZAR-endpoint-de-foundry")
    with pytest.raises(RuntimeError, match="FOUNDRY_AI_ENDPOINT"):
        FoundryRuleEvaluator()
    _foundry(monkeypatch, foundry_ai_endpoint="http://x.example")
    with pytest.raises(RuntimeError, match="https"):
        FoundryRuleEvaluator()


# --- Embeddings de Foundry -----------------------------------------------------------------------------
def _foundry_emb(monkeypatch, **over):
    _foundry(monkeypatch, foundry_ai_embed_deployment="emb-3-large", foundry_embed_dim=4, embedding_provider="foundry")
    for k, v in over.items():
        monkeypatch.setattr(settings, k, v)


def test_foundry_embeddings_batch_normalize_and_keep_order(monkeypatch):
    from app.retrieval.embeddings import FoundryEmbeddingProvider, get_embedding_provider

    _foundry_emb(monkeypatch)
    emb = get_embedding_provider()
    assert isinstance(emb, FoundryEmbeddingProvider)
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append((str(req.url), req.headers["api-key"], len(body["input"])))
        # índices devueltos al revés: el proveedor debe reordenarlos
        data = [{"index": i, "embedding": [float(i + 1), 0, 0, 0]} for i in range(len(body["input"]))][::-1]
        return httpx.Response(200, json={"data": data})

    emb._client = httpx.Client(base_url=emb._client.base_url, params=emb._client.params, headers=emb._client.headers,
                               transport=httpx.MockTransport(handler))
    out = emb.embed([f"t{i}" for i in range(20)])  # 16 + 4
    assert out.shape == (20, 4) and [s[2] for s in seen] == [16, 4]
    assert seen[0][0] == "https://rec.openai.azure.com/openai/deployments/emb-3-large/embeddings?api-version=2024-10-21"
    assert seen[0][1] == "tok" and abs(float((out[0] ** 2).sum()) - 1.0) < 1e-6


def test_foundry_embeddings_never_fall_back_to_mock(monkeypatch):
    from app.retrieval.embeddings import get_embedding_provider

    _foundry_emb(monkeypatch, foundry_ai_embed_deployment="REEMPLAZAR-deployment-de-embeddings")
    with pytest.raises(RuntimeError, match="FOUNDRY_AI_EMBED_DEPLOYMENT"):
        get_embedding_provider()


def test_foundry_embeddings_fail_visibly_and_check_dimension(monkeypatch):
    from app.retrieval.embeddings import get_embedding_provider

    monkeypatch.setattr("time.sleep", lambda s: None)
    _foundry_emb(monkeypatch)
    emb = get_embedding_provider()
    emb._client = httpx.Client(base_url=emb._client.base_url, transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(RuntimeError, match="Foundry"):
        emb.embed(["x"])
    emb._client = httpx.Client(base_url=emb._client.base_url, transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]})))
    with pytest.raises(RuntimeError, match="dimensiones"):
        emb.embed(["x"])


def test_production_start_requires_foundry_config(monkeypatch):
    from app.main import validate_runtime_config

    _foundry_emb(monkeypatch, foundry_ai_embed_deployment="", llm_provider="foundry")
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_mode", "databricks")
    with pytest.raises(RuntimeError, match="EMBEDDING_PROVIDER=foundry"):
        validate_runtime_config()

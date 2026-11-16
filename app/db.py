"""Configuración de SQLAlchemy. Usa SQLite en desarrollo; los modelos son
compatibles con PostgreSQL sin cambios (tipos estándar, sin dialect-specific)."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _build_engine() -> Engine:
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, connect_args=connect_args)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app import models  # noqa: F401  (registra los modelos en Base.metadata)

    Base.metadata.create_all(bind=engine)

    # `create_all` no modifica tablas existentes. Esta migración mínima mantiene
    # el MVP SQLite compatible entre commits sin eliminar datos. En producción
    # debe sustituirse por Alembic.
    if engine.dialect.name == "sqlite":
        columns = {column["name"] for column in inspect(engine).get_columns("analyses")}
        with engine.begin() as connection:
            if "analysis_trace" not in columns:
                connection.execute(text("ALTER TABLE analyses ADD COLUMN analysis_trace JSON"))
            finding_columns = {column["name"] for column in inspect(engine).get_columns("findings")}
            if "trace" not in finding_columns:
                connection.execute(text("ALTER TABLE findings ADD COLUMN trace JSON"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

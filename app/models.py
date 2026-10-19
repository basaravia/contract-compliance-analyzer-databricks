"""Modelos ORM (SQLAlchemy 2.0). Diseñados para migrar a PostgreSQL sin cambios
de esquema: solo tipos estándar (String, Integer, Float, Boolean, DateTime, JSON, Text)."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class DocumentType(str, enum.Enum):
    normativa = "normativa"
    contrato = "contrato"


class ExtractionStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    failed = "failed"
    scanned_no_ocr = "scanned_no_ocr"


class FindingStatus(str, enum.Enum):
    cumple = "cumple"
    no_cumple = "no_cumple"
    parcial = "parcial"
    no_determinable = "no_determinable"
    requiere_revision = "requiere_revision"


class Severity(str, enum.Enum):
    alta = "alta"
    media = "media"
    baja = "baja"


class AnalysisStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    doc_type: Mapped[DocumentType] = mapped_column(SAEnum(DocumentType), nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    stored_filename: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    jurisdiction: Mapped[str] = mapped_column(String, default="EC")
    language: Mapped[str] = mapped_column(String, default="es")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    is_scanned: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SAEnum(ExtractionStatus), default=ExtractionStatus.pending
    )
    uploaded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String, default="EC")
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str] = mapped_column(String, default="media")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    references: Mapped[list["RuleReference"]] = relationship(
        "RuleReference", back_populates="rule", cascade="all, delete-orphan"
    )


class RuleReference(Base):
    __tablename__ = "rule_references"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"), nullable=False)
    normative_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    citation: Mapped[str] = mapped_column(String, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)

    rule: Mapped["Rule"] = relationship("Rule", back_populates="references")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    contract_document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default=AnalysisStatus.pending.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rule_ids: Mapped[list] = mapped_column(JSON, default=list)
    analysis_trace: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), nullable=False)
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normative_refs: Mapped[list] = mapped_column(JSON, default=list)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox_x0: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y0: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_x1: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y1: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[str] = mapped_column(String, default="media")
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    trace: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


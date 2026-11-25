export type FindingStatus = "cumple" | "no_cumple" | "parcial" | "no_determinable" | "requiere_revision";
export type Severity = "alta" | "media" | "baja";
export type DocType = "contrato" | "normativa";

export const STATUS_LABELS: Record<FindingStatus, string> = {
  cumple: "Cumple",
  no_cumple: "No cumple",
  parcial: "Parcial",
  no_determinable: "No determinable",
  requiere_revision: "Requiere revisión",
};

/** Qué significa cada resultado, en lenguaje de auditoría (se muestra en «¿Cómo leer los resultados?»). */
export const STATUS_HELP: Record<FindingStatus, string> = {
  cumple: "El contrato cubre el criterio. Hay un fragmento que lo respalda.",
  no_cumple: "El contrato no cubre el criterio o lo contradice.",
  parcial: "Lo cubre solo en parte: falta algún elemento que el criterio exige.",
  no_determinable: "No hay texto suficiente para decidir (por ejemplo, un PDF escaneado).",
  requiere_revision: "La IA no está segura. Revísalo tú en el PDF antes de concluir.",
};

export const SEVERITY_LABELS: Record<Severity, string> = { alta: "Alta", media: "Media", baja: "Baja" };
export const DOC_TYPE_LABELS: Record<DocType, string> = { contrato: "Contrato", normativa: "Normativa" };
export const EXTRACTION_LABELS: Record<string, string> = {
  done: "Listo",
  pending: "Procesando",
  scanned_no_ocr: "Escaneado: sin texto legible",
  failed: "No se pudo leer",
};

export interface User {
  email: string;
  name: string;
  auth_mode: string;
}

export interface DocumentOut {
  id: string;
  doc_type: DocType;
  original_filename: string;
  title: string | null;
  jurisdiction: string;
  language: string;
  page_count: number;
  is_scanned: boolean;
  extraction_status: string;
  uploaded_at: string;
  file_size_bytes: number;
}

export interface RuleReference {
  id?: string;
  normative_document_id?: string | null;
  citation: string;
  page: number | null;
}

export interface Rule {
  id: string;
  name: string;
  description: string;
  jurisdiction: string;
  category: string | null;
  severity: Severity;
  active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  references: RuleReference[];
}

export interface RuleInput {
  name: string;
  description: string;
  jurisdiction?: string;
  category?: string | null;
  severity: Severity;
  active?: boolean;
  references: { citation: string; page: number | null }[];
}

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface FindingTrace {
  method_summary: string;
  grader_provider: string;
  grader_model: string | null;
  limitations: string[];
  second_pass?: string | null;
  chunks_scanned?: number | null;
  chunks_total?: number | null;
}

export interface Finding {
  id: string;
  analysis_id: string;
  rule_id: string;
  status: FindingStatus;
  justification: string;
  evidence_text: string | null;
  normative_refs: { citation?: string; page?: number | null }[];
  page: number | null;
  bbox_x0: number | null;
  bbox_y0: number | null;
  bbox_x1: number | null;
  bbox_y1: number | null;
  confidence: number;
  severity: Severity;
  is_manual: boolean;
  edited: boolean;
  trace: FindingTrace | null;
  ai_instructions: string | null;
  /** Tramos de una cláusula que continúa en otras páginas (el primero va en page/bbox_*). */
  extra_regions?: { page: number; x0: number; y0: number; x1: number; y1: number }[];
  updated_at: string;
}

export interface Analysis {
  id: string;
  contract_document_id: string;
  status: string;
  error_message: string | null;
  created_by: string | null;
  created_at: string;
  finished_at: string | null;
  rule_ids: string[];
}

export interface AnalysisProgress {
  status: "running" | "done" | "failed" | "interrupted";
  error_message: string | null;
  live: {
    phase: number;
    phases: string[];
    done: number;
    total: number;
    detail: string;
    started_ts: number;
    updated_ts: number;
    now_ts: number;
  } | null;
}

export const ANALYSIS_STATUS_LABELS: Record<string, string> = {
  pending: "En cola",
  running: "En curso",
  done: "Terminado",
  failed: "Falló",
  interrupted: "Interrumpido",
};

export interface AnalysisDetail extends Analysis {
  findings: Finding[];
}

export interface ImportError {
  bloque: number | string;
  error: string;
}

/** Propuesta de la IA para un recuadro: no se guarda hasta que el auditor la acepta. */
export interface RegionProposal {
  status: FindingStatus;
  justification: string;
  evidence_text: string | null;
  confidence: number;
  has_text: boolean;
}

export interface RulePreview {
  rules: RuleInput[];
  errors: { ref: string; error: string }[];
}

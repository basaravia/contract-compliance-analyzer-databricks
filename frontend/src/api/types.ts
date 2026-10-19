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

export interface AnalysisDetail extends Analysis {
  findings: Finding[];
}

export interface ImportError {
  bloque: number | string;
  error: string;
}

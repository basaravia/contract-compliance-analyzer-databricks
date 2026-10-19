import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiJson } from "./client";
import type {
  Analysis,
  AnalysisDetail,
  BBox,
  DocType,
  DocumentOut,
  Finding,
  FindingStatus,
  Rule,
  RuleInput,
  User,
} from "./types";

export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => api<User>("/auth/me"), retry: false });

export const useDocuments = () => useQuery({ queryKey: ["documents"], queryFn: () => api<DocumentOut[]>("/api/documents") });
export const useRules = () => useQuery({ queryKey: ["rules"], queryFn: () => api<Rule[]>("/api/rules") });
export const useAnalyses = () => useQuery({ queryKey: ["analyses"], queryFn: () => api<Analysis[]>("/api/analyses") });
export const useAnalysis = (id: string | undefined) =>
  useQuery({ queryKey: ["analysis", id], queryFn: () => api<AnalysisDetail>(`/api/analyses/${id}`), enabled: !!id });
export const useDocument = (id: string | undefined) =>
  useQuery({ queryKey: ["document", id], queryFn: () => api<DocumentOut>(`/api/documents/${id}`), enabled: !!id });

function useInvalidating<TArg, TRes>(fn: (arg: TArg) => Promise<TRes>, keys: string[][]) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey }))),
  });
}

export const useUploadDocument = () =>
  useInvalidating(
    (v: { docType: DocType; title: string; jurisdiction: string; file: File }) => {
      const form = new FormData();
      form.set("doc_type", v.docType);
      if (v.title) form.set("title", v.title);
      form.set("jurisdiction", v.jurisdiction);
      form.set("file", v.file);
      return api<DocumentOut>("/api/documents", { method: "POST", body: form });
    },
    [["documents"]],
  );

export const useDeleteDocument = () =>
  useInvalidating((id: string) => api<void>(`/api/documents/${id}`, { method: "DELETE" }), [["documents"]]);

export const useCreateRule = () =>
  useInvalidating((r: RuleInput) => apiJson<Rule>("/api/rules", "POST", r), [["rules"]]);
export const useUpdateRule = () =>
  useInvalidating((v: { id: string; patch: Partial<RuleInput> }) => apiJson<Rule>(`/api/rules/${v.id}`, "PUT", v.patch), [
    ["rules"],
  ]);
export const useDeleteRule = () =>
  useInvalidating((id: string) => api<void>(`/api/rules/${id}`, { method: "DELETE" }), [["rules"]]);
export const useImportRules = () =>
  useInvalidating(
    (v: { kind: "json"; payload: unknown } | { kind: "text"; text: string }) =>
      v.kind === "json"
        ? apiJson<Rule[]>("/api/rules/import", "POST", v.payload)
        : apiJson<Rule[]>("/api/rules/import-text", "POST", { text: v.text }),
    [["rules"]],
  );

export const useRunAnalysis = () =>
  useInvalidating(
    (v: { contractId: string; ruleIds: string[] }) =>
      apiJson<AnalysisDetail>("/api/analyses", "POST", { contract_document_id: v.contractId, rule_ids: v.ruleIds }),
    [["analyses"]],
  );

export function useFindingMutations(analysisId: string) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["analysis", analysisId] });
  return {
    moveBbox: useMutation({
      mutationFn: (v: { id: string; bbox: BBox }) =>
        apiJson<Finding>(`/api/findings/${v.id}`, "PATCH", { bbox: v.bbox, recalculate: true }),
      onSuccess: refresh,
    }),
    setStatus: useMutation({
      mutationFn: (v: { id: string; status: FindingStatus }) =>
        apiJson<Finding>(`/api/findings/${v.id}`, "PATCH", { status: v.status, recalculate: false }),
      onSuccess: refresh,
    }),
    create: useMutation({
      mutationFn: (v: { ruleId: string; page: number; bbox: BBox }) =>
        apiJson<Finding>("/api/findings", "POST", {
          analysis_id: analysisId,
          rule_id: v.ruleId,
          page: v.page,
          bbox: v.bbox,
        }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api<void>(`/api/findings/${id}`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function mount(path = "/documentos") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("App", () => {
  it("en Databricks muestra el correo del SSO y no ofrece «Cerrar sesión»", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/auth/me") return json({ email: "ana@example.com", name: "Ana", auth_mode: "databricks" });
      return json([]);
    });
    mount();
    expect(await screen.findByText("ana@example.com")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cerrar sesión/i })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Subir documento" })).toBeInTheDocument();
  });

  it("con 401 no muestra formulario de contraseña, solo el aviso de acceso por el workspace", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input) === "/auth/me" ? json({ detail: "No autenticado" }, 401) : json([]),
    );
    mount();
    expect(await screen.findByText(/Abre la aplicación desde tu workspace/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Contraseña")).not.toBeInTheDocument();
  });

  it("cargar criterios: primero se revisa, se ven los errores por fila y solo después se importa", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/auth/me") return json({ email: "a@b.c", name: "A", auth_mode: "databricks" });
      if (url === "/api/rules/preview-text")
        return json({
          rules: [{ name: "Datos personales", description: "d", severity: "alta", jurisdiction: "EC", references: [{ citation: "LOPDP Art. 5" }] }],
          errors: [{ ref: "Bloque 2", error: "falta Descripción" }],
        });
      if (url === "/api/rules/import" && init?.method === "POST") return json([{ id: "r1" }], 201);
      return json([]);
    });
    mount("/reglas");
    await userEvent.click(await screen.findByRole("radio", { name: /Pegar texto/ }));
    await userEvent.type(screen.getByLabelText("Texto de criterios"), "Regla: x");
    await userEvent.click(screen.getByRole("button", { name: "Revisar antes de cargar" }));
    expect(await screen.findByText(/Bloque 2:/)).toBeInTheDocument();
    expect(screen.getByText("falta Descripción")).toBeInTheDocument();
    expect(screen.getByText("Datos personales")).toBeInTheDocument();
    expect(calls).not.toContain("POST /api/rules/import"); // aún no se guardó nada
    await userEvent.click(screen.getByRole("button", { name: "Cargar 1 criterio" }));
    expect(await screen.findByText(/Se cargaron 1 criterio/)).toBeInTheDocument();
    expect(calls).toContain("POST /api/rules/import");
  });

  it("al subir un PDF muestra el avance y termina con éxito (sin el error de `reset`)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input) === "/auth/me" ? json({ email: "a@b.c", name: "A", auth_mode: "databricks" }) : json([]),
    );
    class FakeXHR {
      status = 0;
      responseText = "";
      upload: { onprogress: ((ev: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = { onprogress: null };
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      withCredentials = false;
      open() {}
      setRequestHeader() {}
      send() {
        this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
        setTimeout(() => {
          this.status = 201;
          this.responseText = JSON.stringify({ id: "d1", title: "Contrato X", original_filename: "x.pdf", page_count: 3 });
          this.onload?.();
        }, 0);
      }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    mount();
    const file = new File(["%PDF-1.4"], "x.pdf", { type: "application/pdf" });
    await userEvent.upload(await screen.findByLabelText("Archivo PDF"), file);
    // jsdom no da por válido un input de archivo `required` aunque tenga archivo: se envía el formulario directamente.
    fireEvent.submit(screen.getByRole("button", { name: "Subir" }).closest("form")!);
    expect(await screen.findByText("Listo: «Contrato X» (3 páginas).")).toBeInTheDocument();
    expect(screen.queryByText(/reset/)).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("un análisis en curso muestra la etapa, el criterio actual y el avance", async () => {
    const now = 1_000_000;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/auth/me") return json({ email: "a@b.c", name: "A", auth_mode: "databricks" });
      if (url === "/api/analyses/a1")
        return json({ id: "a1", contract_document_id: "d1", status: "running", error_message: null, created_by: null,
          created_at: "2026-01-01T00:00:00", finished_at: null, rule_ids: ["r1", "r2", "r3"], findings: [] });
      if (url === "/api/analyses/a1/progress")
        return json({ status: "running", error_message: null, live: {
          phase: 2, phases: ["Leyendo el contrato", "Preparando la búsqueda", "Evaluando criterios", "Guardando resultados"],
          done: 1, total: 3, detail: "Plazo de entrega", started_ts: now - 30, updated_ts: now - 2, now_ts: now } });
      return json([]);
    });
    mount("/analisis/a1");
    expect(await screen.findByText("Evaluando criterio 2 de 3")).toBeInTheDocument();
    expect(screen.getByText(/Plazo de entrega/)).toBeInTheDocument();
    expect(screen.getByText("Evaluando criterios")).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("progressbar", { name: "Avance del análisis" })).toHaveAttribute("aria-valuenow", "38");
    expect(screen.getByText(/Falta aproximadamente/)).toBeInTheDocument();
  });

  const RULES = [
    { id: "r1", name: "Plazo de entrega", description: "d", severity: "alta", active: true, jurisdiction: "EC", references: [], category: null },
    { id: "r2", name: "Confidencialidad", description: "d", severity: "media", active: true, jurisdiction: "EC", references: [], category: null },
  ];

  it("en «Criterios a evaluar» una casilla marca y desmarca todos, y avisa cuántos hay marcados", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/auth/me") return json({ email: "a@b.c", name: "A", auth_mode: "databricks" });
      if (url === "/api/rules") return json(RULES);
      if (url.startsWith("/api/documents")) return json([{ id: "d1", doc_type: "contrato", title: "Contrato", original_filename: "c.pdf", jurisdiction: "EC", page_count: 2, extraction_status: "done", uploaded_at: "2026-01-01T00:00:00" }]);
      return json([]);
    });
    mount("/analisis");
    const all = await screen.findByRole("checkbox", { name: "Marcar todos" });
    expect(screen.getByText(/Ninguno marcado: se evaluarán los 2/)).toBeInTheDocument();
    await userEvent.click(all);
    expect(screen.getByText("2 de 2 marcados")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Plazo de entrega" })).toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "Desmarcar todos" }));
    expect(screen.getByRole("checkbox", { name: "Plazo de entrega" })).not.toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "Confidencialidad" }));
    expect(screen.getByText("1 de 2 marcados")).toBeInTheDocument();
  });

  it("en los resultados la justificación se despliega por fila, con la evidencia y su página", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/auth/me") return json({ email: "a@b.c", name: "A", auth_mode: "databricks" });
      if (url === "/api/rules") return json(RULES);
      if (url === "/api/analyses/a1")
        return json({ id: "a1", contract_document_id: "d1", status: "done", error_message: null, created_by: null,
          created_at: "2026-01-01T00:00:00", finished_at: "2026-01-01T00:01:00", rule_ids: ["r1"],
          findings: [{ id: "f1", analysis_id: "a1", rule_id: "r1", status: "cumple", justification: "La cláusula quinta fija diez días.",
            evidence_text: "El plazo será de diez días.", normative_refs: [], page: 5, bbox_x0: 1, bbox_y0: 1, bbox_x1: 2, bbox_y1: 2,
            confidence: 0.9, severity: "alta", is_manual: false, edited: false, trace: null, ai_instructions: null,
            extra_regions: [{ page: 6, x0: 1, y0: 1, x1: 2, y1: 2 }], updated_at: "2026-01-01T00:01:00" }] });
      return json([]);
    });
    mount("/analisis/a1");
    const toggle = await screen.findByRole("button", { name: /Plazo de entrega/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Evidencia en el contrato", { exact: false })).not.toBeInTheDocument();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("El plazo será de diez días.")).toBeInTheDocument();
    expect(screen.getByText(/Evidencia en el contrato \(p\. 5–6\)/)).toBeInTheDocument();
  });
});

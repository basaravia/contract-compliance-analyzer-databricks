import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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

  it("la importación de reglas en texto lista los errores de formato por bloque", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/auth/me") return json({ email: "a@b.c", name: "A", auth_mode: "databricks" });
      if (url === "/api/rules/import-text" && init?.method === "POST")
        return json({ detail: { message: "Formato inválido", errors: [{ bloque: 2, error: "falta Descripción" }] } }, 422);
      return json([]);
    });
    mount("/reglas");
    await userEvent.type(await screen.findByLabelText("Texto de reglas"), "Regla: x");
    await userEvent.click(screen.getByRole("button", { name: "Importar texto" }));
    await waitFor(() => expect(screen.getByText(/Bloque 2: falta Descripción/)).toBeInTheDocument());
    expect(screen.getByText("Formato inválido")).toBeInTheDocument();
  });
});

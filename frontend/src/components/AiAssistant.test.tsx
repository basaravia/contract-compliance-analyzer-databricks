import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { RegionProposal } from "../api/types";
import { AiAssistant } from "./AiAssistant";

const proposal: RegionProposal = { status: "cumple", justification: "La cláusula lo cubre.", evidence_text: "texto citado", confidence: 0.8, has_text: true };

describe("AiAssistant", () => {
  it("la IA propone y no se guarda nada hasta que la persona acepta", async () => {
    const analyze = vi.fn().mockResolvedValue(proposal);
    const accept = vi.fn().mockResolvedValue(undefined);
    render(<AiAssistant analyze={analyze} accept={accept} acceptLabel="Aceptar y guardar" />);
    await userEvent.type(screen.getByLabelText(/Indicaciones para la IA/), "solo días hábiles");
    await userEvent.click(screen.getByRole("button", { name: "Analizar con IA" }));
    expect(await screen.findByText("La cláusula lo cubre.")).toBeInTheDocument();
    expect(screen.getByText(/Nivel de certeza: Alta/)).toBeInTheDocument();
    expect(analyze).toHaveBeenCalledWith("solo días hábiles", false);
    expect(accept).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Aceptar y guardar" }));
    await waitFor(() => expect(accept).toHaveBeenCalledWith(proposal, "solo días hábiles"));
  });

  it("descartar la propuesta no guarda y un error se muestra en lenguaje claro", async () => {
    const analyze = vi.fn().mockResolvedValueOnce(proposal).mockRejectedValueOnce(new Error("No se pudo analizar con IA ahora. Inténtalo de nuevo."));
    const accept = vi.fn();
    render(<AiAssistant analyze={analyze} accept={accept} acceptLabel="Aceptar" />);
    await userEvent.click(screen.getByRole("button", { name: "Analizar con IA" }));
    await userEvent.click(await screen.findByRole("button", { name: "Descartar" }));
    expect(screen.queryByText("La cláusula lo cubre.")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Analizar con IA" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo analizar con IA ahora");
    expect(accept).not.toHaveBeenCalled();
  });

  it("avisa cuando el recuadro no tiene texto legible", async () => {
    const analyze = vi.fn().mockResolvedValue({ ...proposal, status: "requiere_revision", has_text: false, evidence_text: null, confidence: 0 });
    render(<AiAssistant analyze={analyze} accept={vi.fn()} acceptLabel="Aceptar" />);
    await userEvent.click(screen.getByRole("button", { name: "Analizar con IA" }));
    expect(await screen.findByText(/no contiene texto que se pueda leer/)).toBeInTheDocument();
  });
});

import { Sparkles } from "lucide-react";

/** Marca visual de «esto lo hizo la IA»: destellos y degradado, como en los asistentes de uso común. */
export function AiBadge({ children = "IA" }: { children?: string }) {
  return (
    <span className="ai-badge" title="Generado con inteligencia artificial: revísalo antes de darlo por bueno">
      <Sparkles size={12} aria-hidden="true" /> {children}
    </span>
  );
}

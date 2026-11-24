import { Check, CircleHelp, Eye, TriangleAlert, X, type LucideIcon } from "lucide-react";
import { STATUS_LABELS, type FindingStatus } from "../api/types";

const ICONS: Record<FindingStatus, LucideIcon> = {
  cumple: Check,
  no_cumple: X,
  parcial: TriangleAlert,
  no_determinable: CircleHelp,
  requiere_revision: Eye,
};

export function StatusPill({ status }: { status: FindingStatus }) {
  const Icon = ICONS[status] ?? CircleHelp;
  return (
    <span className={"status-pill status-" + status}>
      <Icon size={12} strokeWidth={3} /> {STATUS_LABELS[status] ?? status}
    </span>
  );
}

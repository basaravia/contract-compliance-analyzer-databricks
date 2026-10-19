import { STATUS_LABELS, type FindingStatus } from "../api/types";

export function StatusPill({ status }: { status: FindingStatus }) {
  return <span className={"status-pill status-" + status}>{STATUS_LABELS[status] ?? status}</span>;
}

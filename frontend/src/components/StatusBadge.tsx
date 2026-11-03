export function StatusBadge({ status }: { status: "active" | "revoked" }) {
  const cls = status === "active" ? "bg-green-100 text-green-800" : "bg-gray-200 text-gray-700";
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>;
}

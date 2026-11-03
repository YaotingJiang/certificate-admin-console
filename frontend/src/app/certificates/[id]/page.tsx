"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type CertificateDetail } from "@/lib/api";
import { useActor } from "@/lib/actor";

export default function CertificateDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { actor, ready } = useActor();
  const [cert, setCert] = useState<CertificateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState(false);

  useEffect(() => {
    if (!ready || !actor) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api<CertificateDetail>(`/api/certificates/${id}`, {}, actor)
      .then((c) => !cancelled && setCert(c))
      .catch((e) => {
        if (cancelled) return;
        setCert(null);
        setError(e.message);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id, actor, ready]);

  const revoke = async () => {
    if (!cert || !confirm(`Revoke certificate ${cert.serial} for ${cert.learner_name}? This cannot be undone.`)) return;
    setRevoking(true);
    setError(null);
    try {
      setCert(await api<CertificateDetail>(`/api/certificates/${id}/revoke`, { method: "POST" }, actor));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRevoking(false);
    }
  };

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-blue-700 underline">
        ← Back to list
      </Link>
      {loading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="rounded bg-red-50 p-2 text-sm text-red-700">Error: {error}</p>}
      {cert && (
        <>
          <section className="rounded-lg border bg-white p-4">
            <div className="flex items-start justify-between">
              <h1 className="font-mono text-lg">{cert.serial}</h1>
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${
                  cert.status === "active" ? "bg-green-100 text-green-800" : "bg-gray-200 text-gray-700"
                }`}
              >
                {cert.status}
              </span>
            </div>
            <dl className="mt-4 grid grid-cols-[10rem_1fr] gap-y-2 text-sm">
              <dt className="text-gray-500">Learner</dt>
              <dd>{cert.learner_name}</dd>
              <dt className="text-gray-500">Course</dt>
              <dd>{cert.course_title}</dd>
              <dt className="text-gray-500">Tenant</dt>
              <dd>
                {cert.tenant.name} ({cert.tenant.timezone})
              </dd>
              <dt className="text-gray-500">Issued (tenant local)</dt>
              <dd>
                {cert.issued_at_local} <span className="text-gray-400">· {cert.issued_at_utc} UTC</span>
              </dd>
              {cert.revoked_at_utc && (
                <>
                  <dt className="text-gray-500">Revoked (UTC)</dt>
                  <dd>{cert.revoked_at_utc}</dd>
                </>
              )}
            </dl>
            {cert.status === "active" && (
              <button
                onClick={revoke}
                disabled={revoking}
                className="mt-4 rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                {revoking ? "Revoking…" : "Revoke certificate"}
              </button>
            )}
          </section>

          <section className="rounded-lg border bg-white p-4">
            <h2 className="mb-2 font-semibold">Audit trail</h2>
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-gray-500">
                <tr>
                  <th className="py-1">When (UTC)</th>
                  <th className="py-1">Action</th>
                  <th className="py-1">Actor</th>
                  <th className="py-1">Operation</th>
                </tr>
              </thead>
              <tbody>
                {cert.audit.map((a) => (
                  <tr key={a.id} className="border-t">
                    <td className="py-1">{a.created_at_utc}</td>
                    <td className="py-1">{a.action}</td>
                    <td className="py-1">{a.actor_email}</td>
                    <td className="py-1 font-mono text-xs text-gray-500">{a.operation_id ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

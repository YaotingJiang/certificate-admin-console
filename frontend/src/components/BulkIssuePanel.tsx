"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type BulkIssueResult } from "@/lib/api";
import { useActor } from "@/lib/actor";

type Course = { id: number; title: string };
type Phase = "idle" | "pending" | "done" | "error";

export function BulkIssuePanel({ onIssued }: { onIssued: () => void }) {
  const { actor } = useActor();
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState<number | "">("");
  // One key per logical attempt: reused on retry after a failure, rotated after success (A2/A3).
  // Generated in an effect, not during render, so Next's prerender sees no unstable value.
  const [idemKey, setIdemKey] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<BulkIssueResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!actor) return;
    setResult(null);
    setError(null);
    setPhase("idle");
    setIdemKey(crypto.randomUUID());
    api<Course[]>("/api/courses", {}, actor)
      .then((c) => {
        setCourses(c);
        setCourseId(c[0]?.id ?? "");
      })
      .catch((e) => setError(e.message));
  }, [actor]);

  const submit = async () => {
    if (courseId === "" || !idemKey || phase === "pending") return;
    setPhase("pending");
    setError(null);
    try {
      const r = await api<BulkIssueResult>("/api/certificates/bulk-issue", {
        method: "POST",
        headers: { "Idempotency-Key": idemKey },
        body: JSON.stringify({ course_id: courseId }),
      });
      setResult(r);
      setPhase("done");
      setIdemKey(crypto.randomUUID());
      onIssued();
    } catch (e) {
      const msg = e instanceof ApiError ? `${e.code}: ${e.message}` : (e as Error).message;
      setError(msg);
      setPhase("error");
    }
  };

  return (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="mb-3 font-semibold">Bulk issue</h2>
      <div className="flex flex-wrap items-center gap-3">
        <select
          className="rounded border border-gray-300 px-2 py-1"
          value={courseId}
          disabled={phase === "pending"}
          onChange={(e) => {
            setCourseId(Number(e.target.value));
            setIdemKey(crypto.randomUUID());
            setResult(null);
            setPhase("idle");
          }}
        >
          {courses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
        <button
          onClick={submit}
          disabled={phase === "pending" || courseId === ""}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {phase === "pending" ? "Issuing…" : "Issue to all eligible learners"}
        </button>
        <span className="text-xs text-gray-500">
          {phase === "pending" && "Operation in progress — button disabled to prevent duplicate submission."}
          {phase === "error" && "Failed. Retrying reuses the same idempotency key."}
          {phase === "done" && result && (result.replayed ? "Replayed existing operation." : "Operation completed.")}
        </span>
      </div>

      {error && <p className="mt-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}

      {result && (
        <div className="mt-4">
          <p className="text-sm">
            <span className="font-medium">{result.course_title}</span> — issued {result.summary.issued}, skipped{" "}
            {result.summary.skipped}, failed {result.summary.failed}
            <span className="ml-2 text-xs text-gray-400">op {result.operation_id.slice(0, 8)}</span>
          </p>
          <table className="mt-2 w-full text-sm">
            <thead className="text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="py-1">Learner</th>
                <th className="py-1">Outcome</th>
                <th className="py-1">Reason</th>
                <th className="py-1">Serial</th>
              </tr>
            </thead>
            <tbody>
              {result.results.map((r) => (
                <tr key={r.learner_id} className="border-t">
                  <td className="py-1">{r.learner_name}</td>
                  <td className="py-1">
                    <OutcomeBadge outcome={r.outcome} />
                  </td>
                  <td className="py-1 text-gray-600">{r.reason ?? "—"}</td>
                  <td className="py-1 font-mono text-xs">{r.serial ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function OutcomeBadge({ outcome }: { outcome: "issued" | "skipped" | "failed" }) {
  const cls =
    outcome === "issued"
      ? "bg-green-100 text-green-800"
      : outcome === "skipped"
        ? "bg-yellow-100 text-yellow-800"
        : "bg-red-100 text-red-800";
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{outcome}</span>;
}

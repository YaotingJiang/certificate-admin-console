"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type BulkIssueResult } from "@/lib/api";

type Course = { id: number; title: string };
type Phase = "idle" | "pending" | "done" | "error";

/** Mounted with key={actor} by the parent, so a tenant switch resets all of this state. */
export function BulkIssuePanel({ actor, onIssued }: { actor: string; onIssued: () => void }) {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [courseId, setCourseId] = useState<number | "">("");
  // One key per logical attempt: created on first submit, reused on retry after a failure,
  // cleared (so a fresh one is made) after success or when the course changes (A2/A3).
  const [idemKey, setIdemKey] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<BulkIssueResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<Course[]>("/api/courses", {}, actor)
      .then((c) => {
        if (cancelled) return;
        setCourses(c);
        setCourseId(c[0]?.id ?? "");
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [actor]);

  const submit = async () => {
    if (courseId === "" || phase === "pending") return;
    const key = idemKey || crypto.randomUUID();
    setIdemKey(key);
    setPhase("pending");
    setError(null);
    try {
      const r = await api<BulkIssueResult>(
        "/api/certificates/bulk-issue",
        { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ course_id: courseId }) },
        actor,
      );
      setResult(r);
      setPhase("done");
      setIdemKey("");
      onIssued();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : (e as Error).message);
      setPhase("error");
    }
  };

  return (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="mb-1 font-semibold">Bulk issue</h2>
      <p className="mb-3 text-xs text-gray-500">
        Issues a certificate to every learner who completed the chosen course and has none yet. Learners with an
        active or revoked certificate are skipped; revoked certificates are never re-issued automatically.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-gray-600" htmlFor="bulk-course">
          Course
        </label>
        <select
          id="bulk-course"
          className="rounded border border-gray-300 px-2 py-1"
          value={courseId}
          disabled={phase === "pending" || courses === null}
          onChange={(e) => {
            setCourseId(Number(e.target.value));
            setIdemKey("");
            setResult(null);
            setError(null);
            setPhase("idle");
          }}
        >
          {courses === null && <option value="">Loading courses…</option>}
          {courses?.map((c) => (
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

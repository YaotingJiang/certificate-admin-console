"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, downloadCsv, type Certificate, type Page } from "@/lib/api";
import { useActor } from "@/lib/actor";
import { BulkIssuePanel } from "@/components/BulkIssuePanel";
import { StatusBadge } from "@/components/StatusBadge";

type SortField = "issued_local_date" | "learner_name" | "serial" | "course_title" | "status";
const PAGE_SIZE = 20;

const COLUMNS: { key: SortField; label: string }[] = [
  { key: "serial", label: "Serial" },
  { key: "learner_name", label: "Learner" },
  { key: "course_title", label: "Course" },
  { key: "issued_local_date", label: "Issued (tenant local)" },
  { key: "status", label: "Status" },
];

type Loaded = { key: string; data?: Page<Certificate>; error?: string };

export default function CertificateListPage() {
  const { actor, ready } = useActor();
  if (!ready) return <p className="text-gray-500">Loading…</p>;
  // Keyed by actor: switching tenant remounts the page and resets search/sort/paging/bulk state.
  return <CertificateList key={actor} actor={actor} />;
}

function CertificateList({ actor }: { actor: string }) {
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortField>("issued_local_date");
  const [dir, setDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [reloadTick, setReloadTick] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const query = new URLSearchParams({ q, sort, dir }).toString();
  const requestKey = `${query}|${page}|${reloadTick}`;

  useEffect(() => {
    let cancelled = false;
    api<Page<Certificate>>(`/api/certificates?${query}&page=${page}&page_size=${PAGE_SIZE}`, {}, actor)
      .then((data) => !cancelled && setLoaded({ key: requestKey, data }))
      .catch((e: Error) => !cancelled && setLoaded({ key: requestKey, error: e.message }));
    return () => {
      cancelled = true;
    };
  }, [actor, query, page, reloadTick, requestKey]);

  // Loading is derived: the last response is for a different request than the current one.
  const current = loaded && loaded.key === requestKey ? loaded : null;
  const loading = current === null;
  const data = current?.data ?? null;
  const error = current?.error ?? null;

  const refresh = useCallback(() => setReloadTick((t) => t + 1), []);

  const toggleSort = (key: SortField) => {
    if (key === sort) setDir(dir === "asc" ? "desc" : "asc");
    else {
      setSort(key);
      setDir(key === "issued_local_date" ? "desc" : "asc");
    }
    setPage(1);
  };

  const onExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      await downloadCsv(query);
    } catch (e) {
      setExportError((e as Error).message);
    } finally {
      setExporting(false);
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="space-y-6">
      <BulkIssuePanel actor={actor} onIssued={refresh} />

      <section className="rounded-lg border bg-white p-4">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h2 className="font-semibold">Certificates</h2>
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setQ(qInput.trim());
              setPage(1);
            }}
          >
            <input
              className="w-64 rounded border border-gray-300 px-2 py-1 text-sm"
              placeholder="Search learner name or serial"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
            />
            <button className="rounded border px-3 py-1 text-sm" type="submit">
              Search
            </button>
            {q && (
              <button
                type="button"
                className="text-sm text-gray-500 underline"
                onClick={() => {
                  setQInput("");
                  setQ("");
                  setPage(1);
                }}
              >
                clear
              </button>
            )}
          </form>
          <div className="ml-auto flex items-center gap-3">
            {data && <span className="text-sm text-gray-500">{data.total.toLocaleString()} total</span>}
            <button
              onClick={onExport}
              disabled={exporting}
              className="rounded border px-3 py-1 text-sm disabled:opacity-50"
              title="Exports the current search and sort"
            >
              {exporting ? "Exporting…" : "Export CSV"}
            </button>
          </div>
        </div>

        {error && <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">Error: {error}</p>}
        {exportError && <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">Export failed: {exportError}</p>}

        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-gray-500">
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} className="cursor-pointer select-none py-2" onClick={() => toggleSort(c.key)}>
                  {c.label}
                  {sort === c.key && <span className="ml-1">{dir === "asc" ? "▲" : "▼"}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-gray-500">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && !error && data && data.items.length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-gray-500">
                  {q ? `No certificates match “${q}”.` : "No certificates yet. Use bulk issue above."}
                </td>
              </tr>
            )}
            {!loading &&
              data?.items.map((c) => (
                <tr key={c.id} className="border-t hover:bg-gray-50">
                  <td className="py-2 font-mono text-xs">
                    <Link className="text-blue-700 underline" href={`/certificates/${c.id}`}>
                      {c.serial}
                    </Link>
                  </td>
                  <td className="py-2">{c.learner_name}</td>
                  <td className="py-2">{c.course_title}</td>
                  <td className="py-2">{c.issued_at_local}</td>
                  <td className="py-2">
                    <StatusBadge status={c.status} />
                  </td>
                </tr>
              ))}
          </tbody>
        </table>

        <div className="mt-3 flex items-center justify-end gap-3 text-sm">
          <button className="rounded border px-2 py-1 disabled:opacity-40" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}>
            ‹ Prev
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            className="rounded border px-2 py-1 disabled:opacity-40"
            disabled={page >= totalPages || loading}
            onClick={() => setPage(page + 1)}
          >
            Next ›
          </button>
        </div>
      </section>
    </div>
  );
}

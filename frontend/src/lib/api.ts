export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const ACTOR_STORAGE_KEY = "cert-admin.actor";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export function readStoredActor(): string {
  try {
    return localStorage.getItem(ACTOR_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

async function toError(res: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `${res.status} ${res.statusText}`;
  try {
    const j = await res.json();
    if (j?.detail?.code) {
      code = j.detail.code;
      message = j.detail.message;
    } else if (typeof j?.detail === "string") {
      message = j.detail;
    } else if (j?.detail) {
      message = JSON.stringify(j.detail);
    }
  } catch {
    /* non-JSON body */
  }
  return new ApiError(res.status, code, message);
}

export async function api<T>(path: string, init: RequestInit = {}, actor = readStoredActor()): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Actor", actor);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) throw await toError(res);
  return res.json() as Promise<T>;
}

/** Export needs the X-Actor header, so it cannot be a plain link: fetch -> blob -> download. */
export async function downloadCsv(query: string) {
  const res = await fetch(`${API_URL}/api/certificates/export.csv?${query}`, {
    headers: { "X-Actor": readStoredActor() },
  });
  if (!res.ok) throw await toError(res);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "certificates.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export type Certificate = {
  id: number;
  serial: string;
  learner_name: string;
  course_title: string;
  status: "active" | "revoked";
  issued_at_utc: string;
  issued_at_local: string;
  issued_local_date: string;
  revoked_at_utc: string | null;
};

export type CertificateDetail = Certificate & {
  tenant: { code: string; name: string; timezone: string };
  audit: { id: number; action: string; actor_email: string; operation_id: string | null; created_at_utc: string }[];
};

export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export type BulkOutcome = {
  learner_id: number;
  learner_name: string;
  outcome: "issued" | "skipped" | "failed";
  reason: string | null;
  serial: string | null;
};

export type BulkIssueResult = {
  operation_id: string;
  course_id: number;
  course_title: string;
  summary: { issued: number; skipped: number; failed: number };
  results: BulkOutcome[];
  replayed: boolean;
};

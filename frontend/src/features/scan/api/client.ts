import type { ApiErrorEnvelope } from "./types.local";

const BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  /* Headers-safe merge: init.headers may be a plain object, a Headers instance,
     or an entries array — spreading only works for the first. */
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let envelope: ApiErrorEnvelope | null = null;
    try {
      envelope = (await res.json()) as ApiErrorEnvelope;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, envelope?.error.code ?? "unknown", envelope?.error.message ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const qs = (params: Record<string, string | number | undefined>): string => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") s.set(k, String(v));
  }
  const str = s.toString();
  return str ? `?${str}` : "";
};

/** Small client for the McXus API. The staff token lives in sessionStorage (gone when the tab closes). */

const KEY = "mcxus.staff.token";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export const token = {
  get: (): string | null => {
    try { return sessionStorage.getItem(KEY); } catch { return null; }
  },
  set: (value: string | null) => {
    try { if (value) sessionStorage.setItem(KEY, value); else sessionStorage.removeItem(KEY); } catch { /* private mode */ }
  },
};

let onSignedOut: () => void = () => {};
export function whenSignedOut(fn: () => void) { onSignedOut = fn; }

async function request<T>(method: string, path: string, body?: unknown, raw = false): Promise<T> {
  const headers: Record<string, string> = {};
  const t = token.get();
  if (t) headers.Authorization = `Bearer ${t}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "offline", "Can't reach the McXus server. Check that the backend is running.");
  }
  if (res.status === 401) { token.set(null); onSignedOut(); }
  if (!res.ok) {
    let code = "error", message = `The server answered ${res.status}`;
    try {
      const data = await res.json();
      if (data?.error) ({ code, message } = data.error);
      else if (Array.isArray(data?.detail)) message = data.detail.map((d: { msg: string }) => d.msg).join("; ");
      else if (typeof data?.detail === "string") message = data.detail;
    } catch { /* not JSON */ }
    if (res.status === 404 && message === "Not Found") {
      message = "The server is older than this console. Rebuild it (task \"McXus: start backend\").";
    }
    throw new ApiError(res.status, code, message);
  }
  if (raw) return (await res.blob()) as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  blob: (path: string) => request<Blob>("GET", path, undefined, true),
};

export function qs(params: Record<string, string | number | boolean | undefined | null | string[]>): string {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => out.append(k, x));
    else out.set(k, String(v));
  }
  const s = out.toString();
  return s ? `?${s}` : "";
}

// Client for the eptask-api service.
//
// Two deployment modes (v2 -- portable build):
//   * gateway mode  (sandbox): requests go to the same origin and Caddy routes
//     them via the XTransformPort query parameter to the Python service.
//     Enabled with NEXT_PUBLIC_GATEWAY_MODE=1.
//   * direct mode   (laptop): requests go straight to the API origin, e.g.
//     http://localhost:8100 (CORS is open). Configured with
//     NEXT_PUBLIC_API_URL; this is the default when the gateway flag is off.
//
// v2 also carries an optional API key (EPTASK_API_KEY on the backend): stored
// in localStorage, sent as X-API-Key on every request and as ?api_key= on
// <img> URLs. A 401 from any call raises the auth gate via the handler
// registered by the app shell.

const API_PORT = "8100";
const GATEWAY = process.env.NEXT_PUBLIC_GATEWAY_MODE === "1";
// gateway mode: same origin (Caddy routes via XTransformPort); direct mode
// (laptop/default): talk to the API origin straight away (CORS is open).
const API_BASE =
  (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "") ||
  (GATEWAY ? "" : `http://localhost:${API_PORT}`);
const KEY_STORAGE = "eptask.api_key";

export type JobKind = "corridor" | "cell" | "outage" | "compare" | "osm";

export function getApiKey(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(KEY_STORAGE) ?? "";
}

export function setApiKey(key: string): void {
  if (typeof window === "undefined") return;
  const k = key.trim();
  if (k) window.localStorage.setItem(KEY_STORAGE, k);
  else window.localStorage.removeItem(KEY_STORAGE);
}

let unauthorizedHandler: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  unauthorizedHandler = fn;
}

function url(path: string, imgAuth = false): string {
  const params = new URLSearchParams();
  if (GATEWAY) params.set("XTransformPort", API_PORT);
  const key = getApiKey();
  if (imgAuth && key) params.set("api_key", key);
  const qs = params.toString();
  const sep = path.includes("?") ? "&" : "?";
  return `${API_BASE}${path}${qs ? sep + qs : ""}`;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `API error ${status}`);
    this.status = status;
    this.detail = detail;
  }
  message_text(): string {
    if (typeof this.detail === "string") return this.detail;
    const d = this.detail as { detail?: unknown };
    if (d && typeof d === "object" && "detail" in d) {
      const arr = d.detail;
      if (Array.isArray(arr)) {
        return arr
          .map((e: { loc?: (string | number)[]; msg?: string }) =>
            `${(e.loc ?? []).slice(1).join(".")}: ${e.msg ?? "invalid"}`)
          .join("; ");
      }
      if (typeof arr === "string") return arr;
    }
    return JSON.stringify(this.detail).slice(0, 300);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const key = getApiKey();
  let res: Response;
  try {
    res = await fetch(url(path), {
      ...init,
      headers: { "Content-Type": "application/json", ...(key ? { "X-API-Key": key } : {}), ...init?.headers },
    });
  } catch (e) {
    throw new ApiError(0, "network error: the simulation service is unreachable");
  }
  if (!res.ok) {
    if (res.status === 401) unauthorizedHandler?.();
    let detail: unknown = res.statusText;
    try {
      detail = await res.json();
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export function fetchMeta() {
  return req<import("./types").MetaInfo>("/api/meta");
}

export function fetchGraph() {
  return req<import("./types").GraphData>("/api/graph");
}

export function fetchGraphSource() {
  return req<import("./types").GraphSourceInfo>("/api/graph/source");
}

export function fetchHealth() {
  return req<import("./types").ServiceCatalogue & { status: string }>("/api/health");
}

export function figureUrl(name: string) {
  return url(`/api/figures/${encodeURIComponent(name)}`, true);
}

export const START = {
  corridor(body: import("./types").CorridorRequest) {
    return req<{ job_id: string }>("/api/corridor/run", { method: "POST", body: JSON.stringify(body) });
  },
  cell(body: import("./types").CellRequest) {
    return req<{ job_id: string }>("/api/cell/run", { method: "POST", body: JSON.stringify(body) });
  },
  outage(body: import("./types").OutageRequest) {
    return req<{ job_id: string }>("/api/outage/run", { method: "POST", body: JSON.stringify(body) });
  },
  compare(body: import("./types").CompareRequest) {
    return req<{ job_id: string }>("/api/corridor/compare", { method: "POST", body: JSON.stringify(body) });
  },
  osm(body: import("./types").OsmBuildRequest) {
    return req<{ job_id: string }>("/api/graph/osm", { method: "POST", body: JSON.stringify(body) });
  },
};

const SUBMIT: Record<JobKind, (body: never) => Promise<{ job_id: string }>> = {
  corridor: START.corridor,
  cell: START.cell,
  outage: START.outage,
  compare: START.compare,
  osm: START.osm,
} as never;

export function poll<T>(jobId: string, signal?: AbortSignal): Promise<import("./types").Job<T>> {
  return req<import("./types").Job<T>>(`/api/jobs/${jobId}`, { signal });
}

/** Submit a job and poll until it finishes. onProgress receives (0..1, stage). */
export async function runJob<T>(
  kind: JobKind,
  body: unknown,
  onProgress?: (frac: number, stage: string) => void,
  pollMs = 700,
): Promise<import("./types").Job<T>> {
  const { job_id } = await SUBMIT[kind](body as never);
  for (;;) {
    const job = await poll<unknown>(job_id);
    if (job.status === "done" && job.result !== null) {
      onProgress?.(1, "done");
      return job as import("./types").Job<T>;
    }
    if (job.status === "error") throw new ApiError(500, job.error ?? "simulation failed");
    onProgress?.(job.progress, job.stage);
    await new Promise((r) => setTimeout(r, pollMs));
  }
}

export function fetchReference<T>(section: string) {
  return req<{ section: string; static: boolean; note: string; data: T }>(
    `/api/reference/${section}`,
  );
}

export function fetchJobs() {
  return req<{ jobs: import("./types").JobListEntry[] }>("/api/jobs");
}

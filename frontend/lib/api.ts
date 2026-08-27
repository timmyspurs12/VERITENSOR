/**
 * Typed API client. All requests go to the same origin and are proxied to the
 * FastAPI backend by next.config.mjs — no backend URL or key is exposed to the
 * browser.
 */
import type {
  ChainStatus, DemoResult, EmissionsPayload, Epoch, GraphPayload, MinerDetail,
  MinerRow, NetworkHealth, NetworkStats, ScoreExplanation, SimulationResult,
  SubnetEvent, TaskDetail, TaskSummary, ValidatorRow,
} from "@/types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  stats: () => request<NetworkStats>("/api/network/stats"),
  health: () => request<NetworkHealth>("/api/system/health"),
  epochs: (limit = 40) => request<Epoch[]>(`/api/network/epochs?limit=${limit}`),
  graph: () => request<GraphPayload>("/api/network/graph"),
  miners: (category?: string, limit = 100) =>
    request<{ total: number; items: MinerRow[] }>(
      `/api/miners?limit=${limit}${category ? `&category=${category}` : ""}`),
  miner: (uid: number) => request<MinerDetail>(`/api/miners/${uid}`),
  validators: () => request<ValidatorRow[]>("/api/validators"),
  tasks: (params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && q.set(k, String(v)));
    return request<{ total: number; limit: number; offset: number; items: TaskSummary[] }>(
      `/api/tasks?${q.toString()}`);
  },
  task: (id: string) => request<TaskDetail>(`/api/tasks/${id}`),
  createTask: (body: { category?: string; difficulty?: number }) =>
    request<TaskDetail>("/api/tasks", { method: "POST", body: JSON.stringify(body) }),
  score: (uid: number, taskId?: string) =>
    request<ScoreExplanation>(`/api/scores/${uid}${taskId ? `?task_id=${taskId}` : ""}`),
  emissions: () => request<EmissionsPayload>("/api/emissions"),
  events: (limit = 60, afterSeq = 0) =>
    request<SubnetEvent[]>(`/api/events?limit=${limit}&after_seq=${afterSeq}`),
  mechanism: () => request<Record<string, any>>("/api/mechanism/config"),
  chainStatus: () => request<ChainStatus>("/api/chain/status"),
  systemInfo: () => request<Record<string, any>>("/api/system/info"),
  runSimulation: (body: {
    miners: number; validators: number; tasks: number; difficulty: string; seed?: number;
  }) => request<SimulationResult>("/api/simulation/run", {
    method: "POST", body: JSON.stringify(body),
  }),
  runDemo: () => request<DemoResult>("/api/demo/run", { method: "POST" }),
  diagnostics: () => request<Record<string, any>>("/api/admin/diagnostics"),
};

export const fetcher = <T,>(path: string): Promise<T> => request<T>(path);

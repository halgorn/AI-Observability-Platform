const QUERY_URL = process.env.NEXT_PUBLIC_QUERY_URL || "http://localhost:8001";
const REPLAY_URL = process.env.NEXT_PUBLIC_REPLAY_URL || "http://localhost:8002";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public request_id?: string) {
    super(message);
  }
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.NEXT_PUBLIC_API_TOKEN || ""}`,
      ...options.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = body.error || {};
    throw new ApiError(res.status, err.code || "UNKNOWN", err.message || res.statusText, err.request_id);
  }
  return res.json();
}

export interface RunSummary {
  run_id: string;
  agent: string;
  status: "running" | "succeeded" | "failed" | "timeout" | "cancelled" | "replaying";
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  total_steps: number | null;
  total_tokens: number | null;
  total_cost_usd: number | null;
}

export interface TraceNode {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: "agent" | "tool" | "llm" | "handoff" | "checkpoint" | "error";
  duration_ms: number;
  started_at: string;
  ended_at: string | null;
  status: "ok" | "error" | "warning";
  children: TraceNode[];
}

export interface Trace {
  roots: TraceNode[];
  summary: { total_events: number; total_cost_usd: number; total_duration_ms: number };
}

export interface ReplaySessionOut {
  session_id: string;
  run_id: string;
  total_steps: number;
  current_step: number;
  mock_llm: boolean;
  mock_tools: string[];
  diverged_at: number | null;
  status: string;
}

export const api = {
  runs: {
    list: (params?: { agent?: string; status?: string; since?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.agent) q.set("agent", params.agent);
      if (params?.status) q.set("status", params.status);
      if (params?.since) q.set("since", params.since);
      if (params?.limit) q.set("limit", String(params.limit));
      const url = `${QUERY_URL}/v1/runs?${q}`;
      return request<{ items: RunSummary[]; count: number; next_cursor: string | null }>(url);
    },
    get: (runId: string) => request<RunSummary>(`${QUERY_URL}/v1/runs/${runId}`),
    trace: (runId: string) => request<Trace>(`${QUERY_URL}/v1/runs/${runId}/trace`),
    events: (runId: string) => request<{ items: any[]; count: number }>(`${QUERY_URL}/v1/runs/${runId}/events`),
    checkpoints: (runId: string) => request<{ items: any[]; count: number }>(`${QUERY_URL}/v1/runs/${runId}/checkpoints`),
  },
  replay: {
    start: (runId: string) => request<ReplaySessionOut>(`${REPLAY_URL}/v1/runs/${runId}/replay`, { method: "POST" }),
    step: (sessionId: string, n = 1) =>
      request<{ step: number; state_hash: string; diverged: boolean }>(
        `${REPLAY_URL}/v1/replay/${sessionId}/step?n=${n}`,
        { method: "POST" },
      ),
    reset: (sessionId: string, toStep = 0) =>
      request<{ step: number; state_hash: string }>(
        `${REPLAY_URL}/v1/replay/${sessionId}/reset?to_step=${toStep}`,
        { method: "POST" },
      ),
    toggle: (sessionId: string, target: string, value: boolean | string) =>
      request<ReplaySessionOut>(`${REPLAY_URL}/v1/replay/${sessionId}/toggle`, {
        method: "POST",
        body: JSON.stringify({ target, value }),
      }),
    run: (sessionId: string) =>
      request<ReplaySessionOut>(`${REPLAY_URL}/v1/replay/${sessionId}/run`, { method: "POST" }),
    status: (sessionId: string) => request<ReplaySessionOut>(`${REPLAY_URL}/v1/replay/${sessionId}/status`),
  },
};

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError, RunSummary } from "@/lib/api";

type Status = "loading" | "error" | "ready";

export function RunsList() {
  const [status, setStatus] = useState<Status>("loading");
  const [items, setItems] = useState<RunSummary[]>([]);
  const [agentFilter, setAgentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = () => {
    api.runs
      .list({ agent: agentFilter || undefined, status: statusFilter || undefined, limit: 50 })
      .then((d) => {
        setItems(d.items);
        setStatus("ready");
      })
      .catch((e) => {
        setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
        setStatus("error");
      });
  };

  useEffect(() => {
    setStatus("loading");
    setError(null);
    fetchRuns();
  }, [agentFilter, statusFilter]);

  useEffect(() => {
    const hasRunning = items.some((r) => r.status === "running");
    if (!hasRunning) return;
    const id = setInterval(fetchRuns, 30_000);
    return () => clearInterval(id);
  }, [items, agentFilter, statusFilter]);

  if (status === "loading") return <div className="p-8 text-zinc-500">Loading runs…</div>;
  if (status === "error")
    return (
      <div className="p-8 text-red-400">
        <p className="font-semibold">Failed to load runs</p>
        <p className="text-sm text-zinc-500 mt-2">{error}</p>
        <p className="text-xs text-zinc-600 mt-4">
          Is query-api running on NEXT_PUBLIC_QUERY_URL? Check .env.
        </p>
      </div>
    );

  return (
    <div className="p-8">
      <div className="flex items-center gap-4 mb-6">
        <input
          type="text"
          placeholder="Filter agent…"
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded text-sm focus:outline-none focus:border-violet-500"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded text-sm"
        >
          <option value="">All statuses</option>
          <option value="running">running</option>
          <option value="succeeded">succeeded</option>
          <option value="failed">failed</option>
          <option value="timeout">timeout</option>
          <option value="cancelled">cancelled</option>
        </select>
        <span className="text-sm text-zinc-500 ml-auto flex items-center gap-2">
          {items.some((r) => r.status === "running") && (
            <span className="flex items-center gap-1 text-xs text-blue-400">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              auto-refresh
            </span>
          )}
          {items.length} runs
        </span>
      </div>
      {items.length === 0 ? (
        <div className="text-zinc-500 text-sm">No runs match the filter.</div>
      ) : (
        <div className="border border-zinc-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900 text-zinc-400 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-2">Run</th>
                <th className="text-left px-4 py-2">Agent</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-right px-4 py-2">Duration</th>
                <th className="text-right px-4 py-2">Cost</th>
                <th className="text-right px-4 py-2">Steps</th>
                <th className="text-left px-4 py-2">Started</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.run_id} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                  <td className="px-4 py-2 font-mono text-xs text-violet-300">
                    <Link href={`/runs/${r.run_id}`}>{r.run_id.slice(0, 8)}…</Link>
                  </td>
                  <td className="px-4 py-2">{r.agent}</td>
                  <td className="px-4 py-2">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{formatDuration(r.duration_ms)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{formatCost(r.total_cost_usd)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{r.total_steps ?? "—"}</td>
                  <td className="px-4 py-2 text-zinc-500 text-xs">{new Date(r.started_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function StatusBadge({ status }: { status: RunSummary["status"] }) {
  const colors: Record<RunSummary["status"], string> = {
    running:    "bg-blue-500/20 text-blue-300",
    succeeded:  "bg-emerald-500/20 text-emerald-300",
    failed:     "bg-red-500/20 text-red-300",
    timeout:    "bg-amber-500/20 text-amber-300",
    cancelled:  "bg-zinc-500/20 text-zinc-300",
    replaying:  "bg-violet-500/20 text-violet-300",
  };
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[status]}`}>{status}</span>;
}

export function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function formatCost(usd: number | null): string {
  if (usd == null) return "—";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

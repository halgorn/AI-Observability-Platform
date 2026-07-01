"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError, RunSummary, Trace } from "@/lib/api";
import { TraceView } from "@/components/TraceView";
import { ReplayStepper } from "@/components/ReplayStepper";
import { StatusBadge, formatCost, formatDuration } from "@/components/RunsList";

export function RunDetail({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunSummary | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedSpan, setSelectedSpan] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.runs.get(runId), api.runs.trace(runId)])
      .then(([r, t]) => {
        setRun(r);
        setTrace(t);
      })
      .catch((e) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
  }, [runId]);

  if (error)
    return (
      <div className="p-8 text-red-400">
        <p className="font-semibold">Failed to load run</p>
        <p className="text-sm text-zinc-500 mt-2">{error}</p>
      </div>
    );
  if (!run || !trace) return <div className="p-8 text-zinc-500">Loading…</div>;

  const selectedNode = selectedSpan ? findNode(trace.roots, selectedSpan) : null;

  return (
    <div className="p-8">
      <header className="mb-6 flex items-baseline gap-4">
        <Link href="/runs" className="text-sm text-zinc-500 hover:text-zinc-300">← runs</Link>
        <h1 className="text-lg font-mono">{run.run_id}</h1>
        <StatusBadge status={run.status} />
        <span className="text-sm text-zinc-400">{run.agent}</span>
        <span className="text-sm text-zinc-500 ml-auto tabular-nums">
          {formatDuration(run.duration_ms)} · {formatCost(run.total_cost_usd)} · {run.total_steps ?? "—"} steps
        </span>
      </header>

      {run.status === "failed" && (
        <div className="mb-6 border border-red-800 bg-red-950/30 rounded-lg p-4">
          <p className="text-xs font-semibold text-red-400 mb-1">
            {trace.summary?.error_type ?? "Run failed"}
          </p>
          {trace.summary?.error_message ? (
            <p className="text-sm text-red-300 font-mono break-words">{trace.summary.error_message}</p>
          ) : (
            <p className="text-xs text-zinc-500">Click an error span in the trace below for details.</p>
          )}
        </div>
      )}

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2">
          <TraceView roots={trace.roots} summary={trace.summary} selectedId={selectedSpan} onSelect={setSelectedSpan} />
        </div>
        <div className="space-y-4">
          {selectedNode && (
            <div className="border border-zinc-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-2">Span</h3>
              <dl className="text-xs space-y-1">
                <div className="flex justify-between"><dt className="text-zinc-500">name</dt><dd className="font-mono">{selectedNode.name}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">kind</dt><dd>{selectedNode.kind}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">status</dt><dd>{selectedNode.status}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">duration</dt><dd>{formatDuration(selectedNode.duration_ms)}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">span_id</dt><dd className="font-mono text-[10px]">{selectedNode.span_id}</dd></div>
              </dl>
            </div>
          )}
          <ReplayStepper runId={runId} />
        </div>
      </div>
    </div>
  );
}

function findNode(roots: Trace["roots"], spanId: string): Trace["roots"][number] | null {
  for (const r of roots) {
    if (r.span_id === spanId) return r;
    const found = findNode(r.children, spanId);
    if (found) return found;
  }
  return null;
}

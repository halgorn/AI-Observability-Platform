"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError, RunSummary, Trace, TraceNode } from "@/lib/api";
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
          {selectedNode && <SpanDetail node={selectedNode} />}
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

function SpanDetail({ node }: { node: TraceNode }) {
  const ev = node.event;
  const payload = ev?.payload ?? {};
  const attrs = ev?.attributes ?? {};
  const errorAttrs = attrs["error.message"] || attrs["error.type"];

  const payloadRows = Object.entries(payload).filter(([, v]) => v !== null && v !== undefined && v !== "");
  const attrRows = Object.entries(attrs).filter(([k, v]) =>
    v !== null && v !== undefined && v !== "" &&
    !["event_type", "genai.agent.name", "genai.tool.name", "genai.llm.model"].includes(k)
  );

  return (
    <div className="border border-zinc-800 rounded-lg p-4 space-y-4">
      <div>
        <h3 className="text-sm font-semibold mb-2">Span</h3>
        <dl className="text-xs space-y-1">
          <Row label="name">{node.name}</Row>
          <Row label="kind">{node.kind}</Row>
          <Row label="status">
            <span className={node.status === "error" ? "text-red-400" : "text-green-400"}>{node.status}</span>
          </Row>
          <Row label="duration">{formatDuration(node.duration_ms)}</Row>
          {ev?.agent && <Row label="agent"><span className="font-mono">{ev.agent}</span></Row>}
          {ev?.tool && <Row label="tool"><span className="font-mono">{ev.tool}</span></Row>}
          {ev?.llm_model && <Row label="model"><span className="font-mono">{ev.llm_model}</span></Row>}
          {ev?.tokens_in != null && <Row label="tokens_in">{ev.tokens_in}</Row>}
          {ev?.tokens_out != null && <Row label="tokens_out">{ev.tokens_out}</Row>}
          {ev?.cost_usd != null && <Row label="cost">{formatCost(ev.cost_usd)}</Row>}
          {ev?.error_code && <Row label="error_code"><span className="text-red-400">{ev.error_code}</span></Row>}
        </dl>
      </div>

      {errorAttrs && (
        <div>
          <h4 className="text-xs font-semibold text-red-400 mb-1">Error</h4>
          <div className="bg-red-950/40 rounded p-2 text-xs font-mono text-red-300 break-words whitespace-pre-wrap">
            {attrs["error.type"] ? `[${attrs["error.type"]}] ` : ""}{String(attrs["error.message"] ?? "")}
          </div>
        </div>
      )}

      {payloadRows.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-zinc-400 mb-1">Payload</h4>
          <div className="bg-zinc-900 rounded p-2 text-xs font-mono space-y-0.5">
            {payloadRows.map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <span className="text-zinc-500 shrink-0">{k}</span>
                <span className="text-zinc-200 break-words">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {attrRows.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-zinc-400 mb-1">Attributes</h4>
          <div className="bg-zinc-900 rounded p-2 text-xs font-mono space-y-0.5 max-h-40 overflow-y-auto">
            {attrRows.map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <span className="text-zinc-500 shrink-0 truncate max-w-[40%]">{k}</span>
                <span className="text-zinc-200 break-words">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <span className="text-[10px] text-zinc-600 font-mono">{node.span_id}</span>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-zinc-500 shrink-0">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

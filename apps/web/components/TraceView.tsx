"use client";

import { useState } from "react";
import { TraceNode } from "@/lib/api";
import { formatDuration, formatCost } from "./RunsList";

interface Props {
  roots: TraceNode[];
  summary: { total_events: number; total_cost_usd: number; total_duration_ms: number };
  selectedId: string | null;
  onSelect: (spanId: string) => void;
}

export function TraceView({ roots, summary, selectedId, onSelect }: Props) {
  return (
    <div className="grid grid-cols-3 gap-6 p-8">
      <div className="col-span-2">
        <div className="mb-4 flex items-baseline gap-4">
          <h2 className="text-lg font-semibold">Trace</h2>
          <span className="text-sm text-zinc-500">
            {summary.total_events} events · {formatDuration(summary.total_duration_ms)} · {formatCost(summary.total_cost_usd)}
          </span>
        </div>
        <div className="space-y-1">
          {roots.length === 0 ? (
            <div className="text-zinc-500 text-sm">No events to display.</div>
          ) : (
            roots.map((node) => <TraceNodeView key={node.span_id} node={node} depth={0} selectedId={selectedId} onSelect={onSelect} />)
          )}
        </div>
      </div>
    </div>
  );
}

function TraceNodeView({ node, depth, selectedId, onSelect }: { node: TraceNode; depth: number; selectedId: string | null; onSelect: (id: string) => void }) {
  const isSelected = node.span_id === selectedId;
  return (
    <div>
      <button
        onClick={() => onSelect(node.span_id)}
        className={`w-full text-left px-3 py-1.5 rounded text-sm flex items-center gap-2 transition-colors ${
          isSelected ? "bg-violet-500/20 text-violet-200" : "hover:bg-zinc-900"
        }`}
        style={{ paddingLeft: `${0.75 + depth * 1.25}rem` }}
      >
        <KindBadge kind={node.kind} />
        <span className="font-mono text-xs truncate">{node.name}</span>
        <span className="ml-auto text-zinc-500 text-xs tabular-nums">{formatDuration(node.duration_ms)}</span>
        {node.status === "error" && <span className="text-red-400 text-xs">error</span>}
      </button>
      {node.children.length > 0 && (
        <div className="mt-1 space-y-1">
          {node.children.map((c) => <TraceNodeView key={c.span_id} node={c} depth={depth + 1} selectedId={selectedId} onSelect={onSelect} />)}
        </div>
      )}
    </div>
  );
}

function KindBadge({ kind }: { kind: TraceNode["kind"] }) {
  const colors: Record<TraceNode["kind"], string> = {
    agent:      "bg-violet-500/20 text-violet-300",
    tool:       "bg-amber-500/20 text-amber-300",
    llm:        "bg-blue-500/20 text-blue-300",
    handoff:    "bg-pink-500/20 text-pink-300",
    checkpoint: "bg-zinc-500/20 text-zinc-300",
    error:      "bg-red-500/20 text-red-300",
  };
  return <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${colors[kind]}`}>{kind}</span>;
}

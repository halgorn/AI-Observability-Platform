"use client";

import { useMemo, useState } from "react";
import { TraceNode } from "@/lib/api";
import { formatDuration, formatCost } from "./RunsList";

interface Props {
  roots: TraceNode[];
  summary: { total_events: number; total_cost_usd: number; total_duration_ms: number };
  selectedId: string | null;
  onSelect: (spanId: string) => void;
}

type KindFilter = "all" | TraceNode["kind"];

export function TraceView({ roots, summary, selectedId, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "ok" | "error">("all");
  const [agentFilter, setAgentFilter] = useState<string>("all");

  const agents = useMemo(() => {
    const set = new Set<string>();
    const walk = (ns: TraceNode[]) => {
      for (const n of ns) {
        if (n.event?.agent) set.add(n.event.agent);
        walk(n.children);
      }
    };
    walk(roots);
    return Array.from(set).sort();
  }, [roots]);

  const flat = useMemo(() => {
    const out: TraceNode[] = [];
    const walk = (ns: TraceNode[]) => {
      for (const n of ns) {
        out.push(n);
        walk(n.children);
      }
    };
    walk(roots);
    return out;
  }, [roots]);

  const filteredIds = useMemo(() => {
    const q = query.trim().toLowerCase();
    const ids = new Set<string>();
    for (const n of flat) {
      if (kindFilter !== "all" && n.kind !== kindFilter) continue;
      if (statusFilter !== "all" && n.status !== statusFilter) continue;
      if (agentFilter !== "all" && (n.event?.agent ?? null) !== agentFilter) continue;
      if (q) {
        const hay = `${n.name} ${n.span_id} ${n.event?.tool ?? ""} ${n.event?.llm_model ?? ""} ${n.event?.error_code ?? ""}`.toLowerCase();
        if (!hay.includes(q)) continue;
      }
      ids.add(n.span_id);
    }
    return ids;
  }, [flat, query, kindFilter, statusFilter, agentFilter]);

  const filteredRoots = useMemo(() => filterTree(roots, filteredIds), [roots, filteredIds]);

  const selectedFlatIndex = useMemo(() => {
    if (!selectedId) return -1;
    return flat.findIndex((n) => n.span_id === selectedId);
  }, [flat, selectedId]);

  const prevId = selectedFlatIndex > 0 ? flat[selectedFlatIndex - 1].span_id : null;
  const nextId = selectedFlatIndex >= 0 && selectedFlatIndex < flat.length - 1 ? flat[selectedFlatIndex + 1].span_id : null;
  const ancestry = useMemo(() => {
    if (!selectedId) return [];
    return findAncestry(roots, selectedId);
  }, [roots, selectedId]);

  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-4">
        <h2 className="text-lg font-semibold">Trace</h2>
        <span className="text-sm text-zinc-500">
          {summary.total_events} events · {formatDuration(summary.total_duration_ms)} · {formatCost(summary.total_cost_usd)}
        </span>
        <span className="text-xs text-zinc-600 ml-auto">
          showing {filteredIds.size}/{flat.length} spans
        </span>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        <input
          type="text"
          placeholder="Search span / id / tool / model…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 px-2 py-1 rounded flex-1 min-w-[12rem] focus:outline-none focus:border-violet-500"
        />
        <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value as KindFilter)} className="bg-zinc-900 border border-zinc-800 px-2 py-1 rounded">
          <option value="all">all kinds</option>
          <option value="agent">agent</option>
          <option value="llm">llm</option>
          <option value="tool">tool</option>
          <option value="handoff">handoff</option>
          <option value="checkpoint">checkpoint</option>
          <option value="error">error</option>
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as any)} className="bg-zinc-900 border border-zinc-800 px-2 py-1 rounded">
          <option value="all">all status</option>
          <option value="ok">ok</option>
          <option value="error">error</option>
        </select>
        {agents.length > 0 && (
          <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} className="bg-zinc-900 border border-zinc-800 px-2 py-1 rounded">
            <option value="all">all agents</option>
            {agents.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        )}
      </div>

      {ancestry.length > 1 && (
        <nav className="text-xs text-zinc-400 flex flex-wrap items-center gap-1">
          <span className="text-zinc-600">ancestry:</span>
          {ancestry.map((n, i) => (
            <span key={n.span_id} className="flex items-center gap-1">
              {i > 0 && <span className="text-zinc-600">›</span>}
              <button
                onClick={() => onSelect(n.span_id)}
                className={`hover:text-violet-300 font-mono ${i === ancestry.length - 1 ? "text-violet-300" : "text-zinc-400"}`}
              >
                {n.name}
              </button>
            </span>
          ))}
        </nav>
      )}

      <div className="flex items-center gap-2 text-xs">
        <button
          disabled={!prevId}
          onClick={() => prevId && onSelect(prevId)}
          className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 rounded disabled:opacity-40 disabled:hover:bg-zinc-800"
        >
          ← prev span
        </button>
        <button
          disabled={!nextId}
          onClick={() => nextId && onSelect(nextId)}
          className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 rounded disabled:opacity-40 disabled:hover:bg-zinc-800"
        >
          next span →
        </button>
      </div>

      <div className="space-y-1">
        {filteredRoots.length === 0 ? (
          <div className="text-zinc-500 text-sm">
            {flat.length === 0 ? "No events to display." : "No spans match the current filters."}
          </div>
        ) : (
          filteredRoots.map((node) => (
            <TraceNodeView key={node.span_id} node={node} depth={0} selectedId={selectedId} onSelect={onSelect} filteredIds={filteredIds} />
          ))
        )}
      </div>
    </div>
  );
}

function filterTree(roots: TraceNode[], allowed: Set<string>): TraceNode[] {
  const out: TraceNode[] = [];
  for (const n of roots) {
    const filteredChildren = filterTree(n.children, allowed);
    if (allowed.has(n.span_id) || filteredChildren.length > 0) {
      out.push({ ...n, children: filteredChildren });
    }
  }
  return out;
}

function findAncestry(roots: TraceNode[], targetId: string): TraceNode[] {
  const trail: TraceNode[] = [];
  function walk(nodes: TraceNode[]): boolean {
    for (const n of nodes) {
      trail.push(n);
      if (n.span_id === targetId) return true;
      if (walk(n.children)) return true;
      trail.pop();
    }
    return false;
  }
  return walk(roots) ? [...trail] : [];
}

function TraceNodeView({
  node, depth, selectedId, onSelect, filteredIds,
}: {
  node: TraceNode; depth: number; selectedId: string | null; onSelect: (id: string) => void; filteredIds: Set<string>;
}) {
  const isSelected = node.span_id === selectedId;
  const matched = filteredIds.has(node.span_id);
  return (
    <div>
      <button
        onClick={() => onSelect(node.span_id)}
        className={`w-full text-left px-3 py-1.5 rounded text-sm flex items-center gap-2 transition-colors ${
          isSelected ? "bg-violet-500/20 text-violet-200" : matched ? "hover:bg-zinc-900" : "opacity-40 hover:opacity-70"
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
          {node.children.map((c) => (
            <TraceNodeView key={c.span_id} node={c} depth={depth + 1} selectedId={selectedId} onSelect={onSelect} filteredIds={filteredIds} />
          ))}
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
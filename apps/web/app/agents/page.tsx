"use client";

import React, { useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  type Node,
  type Edge,
} from "reactflow";
import "reactflow/dist/style.css";
import clsx from "clsx";
import { api, type HandoffEdge } from "../../lib/api";

// ── demo seed ─────────────────────────────────────────────────────────────────
const DEMO_EDGES: HandoffEdge[] = [
  { from: "planner",   to: "executor",  success_count: 45, total_count: 50, success_rate: 0.90 },
  { from: "executor",  to: "validator", success_count: 38, total_count: 42, success_rate: 0.905 },
  { from: "planner",   to: "searcher",  success_count: 28, total_count: 35, success_rate: 0.80 },
  { from: "searcher",  to: "executor",  success_count: 20, total_count: 30, success_rate: 0.667 },
  { from: "validator", to: "planner",   success_count:  8, total_count: 15, success_rate: 0.533 },
];

// ── edge color by success rate ────────────────────────────────────────────────
function edgeColor(rate: number): string {
  if (rate >= 0.9) return "#22c55e";
  if (rate >= 0.7) return "#eab308";
  return "#ef4444";
}

// ── circular node layout ──────────────────────────────────────────────────────
function circularLayout(agents: string[], cx = 360, cy = 220, r = 180): Record<string, { x: number; y: number }> {
  const n = agents.length;
  const pos: Record<string, { x: number; y: number }> = {};
  agents.forEach((a, i) => {
    const angle = (i * 2 * Math.PI) / n - Math.PI / 2;
    pos[a] = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  });
  return pos;
}

// ── build ReactFlow nodes + edges ─────────────────────────────────────────────
function buildGraph(
  items: HandoffEdge[],
  onNodeClick: (agent: string) => void,
): { nodes: Node[]; edges: Edge[] } {
  const agentSet = new Set<string>();
  items.forEach((e) => { agentSet.add(e.from); agentSet.add(e.to); });
  const agents = [...agentSet];
  const pos = circularLayout(agents);

  const nodes: Node[] = agents.map((a) => ({
    id: a,
    position: pos[a],
    data: {
      label: (
        <button
          onClick={() => onNodeClick(a)}
          className="px-3 py-1.5 text-xs font-semibold text-white rounded-lg whitespace-nowrap"
        >
          {a}
        </button>
      ),
    },
    style: {
      background: "#3b0764",
      border: "1.5px solid #7c3aed",
      borderRadius: 10,
      padding: 0,
      width: "auto",
    },
  }));

  const edges: Edge[] = items.map((e, i) => {
    const color = edgeColor(e.success_rate);
    return {
      id: `e-${i}`,
      source: e.from,
      target: e.to,
      label: `${e.total_count} · ${Math.round(e.success_rate * 100)}%`,
      labelStyle: { fill: color, fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 },
      labelBgPadding: [4, 6] as [number, number],
      style: { stroke: color, strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color },
      animated: e.success_rate < 0.7,
    };
  });

  return { nodes, edges };
}

// ── success badge ─────────────────────────────────────────────────────────────
function RateBadge({ rate }: { rate: number }) {
  const pct = Math.round(rate * 100);
  return (
    <span
      className={clsx(
        "inline-block text-xs font-semibold px-2 py-0.5 rounded-full",
        rate >= 0.9 ? "bg-green-900/50 text-green-400" :
        rate >= 0.7 ? "bg-yellow-900/50 text-yellow-400" :
                      "bg-red-900/50 text-red-400",
      )}
    >
      {pct}%
    </span>
  );
}

// ── page ──────────────────────────────────────────────────────────────────────
export default function AgentsPage() {
  const router = useRouter();
  const [since, setSince] = React.useState("7d");

  const { data, error, isLoading } = useSWR(
    `agents-handoffs-${since}`,
    () => api.analytics.handoffs(since),
    { shouldRetryOnError: false, onError: () => {} },
  );

  const isDemo = !!error;
  const items: HandoffEdge[] = data?.items?.length ? data.items : isDemo ? DEMO_EDGES : [];

  const onNodeClick = useCallback(
    (agent: string) => router.push(`/runs?agent=${encodeURIComponent(agent)}`),
    [router],
  );

  const { nodes, edges } = useMemo(() => buildGraph(items, onNodeClick), [items, onNodeClick]);

  // stats
  const uniqueAgents = new Set(items.flatMap((e) => [e.from, e.to])).size;
  const totalHandoffs = items.reduce((s, e) => s + e.total_count, 0);
  const avgRate =
    items.length > 0
      ? items.reduce((s, e) => s + e.success_rate, 0) / items.length
      : 0;

  return (
    <div className="p-8 space-y-8 max-w-6xl mx-auto">
      {/* header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Agents</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Handoff graph — click an agent node to drill into its runs
          </p>
        </div>
        <div className="flex gap-1">
          {["24h", "7d", "30d"].map((w) => (
            <button
              key={w}
              onClick={() => setSince(w)}
              className={clsx(
                "px-3 py-1 rounded text-xs font-medium transition-colors",
                since === w
                  ? "bg-violet-600 text-white"
                  : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700",
              )}
            >
              {w}
            </button>
          ))}
        </div>
      </div>

      {isDemo && (
        <div className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded px-3 py-2">
          Query API offline — showing demo data. Start the query-api to see live handoffs.
        </div>
      )}

      {/* stat cards */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Unique agents", value: isLoading && !isDemo ? "—" : uniqueAgents },
          { label: "Total handoffs", value: isLoading && !isDemo ? "—" : totalHandoffs },
          {
            label: "Avg success rate",
            value: isLoading && !isDemo ? "—" : `${Math.round(avgRate * 100)}%`,
            color: avgRate >= 0.9 ? "text-green-400" : avgRate >= 0.7 ? "text-yellow-400" : "text-red-400",
          },
        ].map((s) => (
          <div key={s.label} className="bg-zinc-900 border border-zinc-800 rounded-xl px-5 py-4">
            <p className="text-xs text-zinc-500 mb-1">{s.label}</p>
            <p className={clsx("text-2xl font-semibold", s.color ?? "text-white")}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* graph */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden" style={{ height: 480 }}>
        {isLoading && !isDemo ? (
          <div className="h-full flex items-center justify-center text-zinc-500 text-sm">Loading…</div>
        ) : items.length === 0 ? (
          <div className="h-full flex items-center justify-center text-zinc-500 text-sm">
            No handoff data for this window
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#3f3f46" gap={24} />
            <Controls showInteractive={false} style={{ background: "#27272a", border: "none" }} />
          </ReactFlow>
        )}
      </div>

      {/* edge table */}
      {items.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-zinc-300 mb-3 uppercase tracking-wider">
            Handoff details
          </h2>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-xs text-zinc-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-3 font-medium">From</th>
                  <th className="text-left px-4 py-3 font-medium">To</th>
                  <th className="text-right px-4 py-3 font-medium">Total</th>
                  <th className="text-right px-4 py-3 font-medium">Success</th>
                  <th className="text-right px-4 py-3 font-medium">Rate</th>
                </tr>
              </thead>
              <tbody>
                {[...items]
                  .sort((a, b) => b.total_count - a.total_count)
                  .map((e, i) => (
                    <tr
                      key={i}
                      className="border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/30 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <button
                          onClick={() => onNodeClick(e.from)}
                          className="text-violet-400 hover:text-violet-300 font-medium"
                        >
                          {e.from}
                        </button>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => onNodeClick(e.to)}
                          className="text-violet-400 hover:text-violet-300 font-medium"
                        >
                          {e.to}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-right text-zinc-300">{e.total_count}</td>
                      <td className="px-4 py-3 text-right text-zinc-300">{e.success_count}</td>
                      <td className="px-4 py-3 text-right">
                        <RateBadge rate={e.success_rate} />
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

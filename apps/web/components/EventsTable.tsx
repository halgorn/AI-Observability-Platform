"use client";

import { useState } from "react";
import { TraceEvent } from "@/lib/api";
import { formatDuration } from "./RunsList";
import { CopyButton, downloadJson } from "./CopyButton";

interface Props {
  events: TraceEvent[];
  runId: string;
  onSelect: (spanId: string) => void;
}

export function EventsTable({ events, runId, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");

  const types = Array.from(new Set(events.map((e) => e.type))).sort();

  const sorted = [...events].sort((a, b) => {
    const ta = new Date(a.started_at).getTime();
    const tb = new Date(b.started_at).getTime();
    if (ta !== tb) return ta - tb;
    return a.span_id.localeCompare(b.span_id);
  });

  const filtered = sorted.filter((e) => {
    if (typeFilter !== "all" && e.type !== typeFilter) return false;
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      const hay = `${e.type} ${e.span_id} ${e.agent ?? ""} ${e.tool ?? ""} ${e.llm_model ?? ""} ${e.error_code ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-4">
        <h2 className="text-lg font-semibold">All events</h2>
        <span className="text-sm text-zinc-500">{filtered.length}/{events.length} events · sorted by started_at</span>
        <div className="ml-auto flex gap-2">
          <CopyButton
            value={JSON.stringify(sorted, null, 2)}
            label="Copy JSON"
            className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded"
          />
          <button
            onClick={() => downloadJson(`${runId}-events.json`, sorted)}
            className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded"
          >
            Download .json
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        <input
          type="text"
          placeholder="Search…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 px-2 py-1 rounded flex-1 min-w-[12rem] focus:outline-none focus:border-violet-500"
        />
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="bg-zinc-900 border border-zinc-800 px-2 py-1 rounded">
          <option value="all">all types</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      {filtered.length === 0 ? (
        <div className="text-zinc-500 text-sm">No events match the filter.</div>
      ) : (
        <div className="border border-zinc-800 rounded-lg overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-zinc-900 text-zinc-400 uppercase tracking-wide">
              <tr>
                <th className="text-left px-3 py-2">t</th>
                <th className="text-left px-3 py-2">type</th>
                <th className="text-left px-3 py-2">agent / tool / model</th>
                <th className="text-right px-3 py-2">duration</th>
                <th className="text-right px-3 py-2">tokens (in/out)</th>
                <th className="text-right px-3 py-2">cost</th>
                <th className="text-left px-3 py-2">status</th>
                <th className="text-left px-3 py-2">span_id</th>
                <th className="text-left px-3 py-2">parent</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => {
                const isError = !!e.error_code || e.type === "error";
                const label = [e.agent, e.tool, e.llm_model].filter(Boolean).join(" · ") || "—";
                return (
                  <tr
                    key={e.span_id}
                    className={`border-t border-zinc-800 hover:bg-zinc-900/50 cursor-pointer ${isError ? "bg-red-950/20" : ""}`}
                    onClick={() => onSelect(e.span_id)}
                  >
                    <td className="px-3 py-1.5 text-zinc-500 font-mono whitespace-nowrap">{new Date(e.started_at).toISOString().slice(11, 23)}</td>
                    <td className="px-3 py-1.5 font-mono">{e.type}</td>
                    <td className="px-3 py-1.5 font-mono truncate max-w-[16rem]">{label}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{formatDuration(e.duration_ms)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {e.tokens_in != null || e.tokens_out != null ? `${e.tokens_in ?? 0}/${e.tokens_out ?? 0}` : "—"}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{e.cost_usd != null ? `$${e.cost_usd.toFixed(4)}` : "—"}</td>
                    <td className={`px-3 py-1.5 ${isError ? "text-red-400" : "text-emerald-400"}`}>{isError ? "error" : "ok"}</td>
                    <td className="px-3 py-1.5 font-mono text-zinc-500">{e.span_id.slice(0, 8)}…</td>
                    <td className="px-3 py-1.5 font-mono text-zinc-500">{e.parent_span_id ? `${e.parent_span_id.slice(0, 8)}…` : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
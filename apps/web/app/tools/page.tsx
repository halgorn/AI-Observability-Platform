"use client";

import useSWR from "swr";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { api, ToolRow, AgentCostRow } from "../../lib/api";
import clsx from "clsx";

// ── palette ──────────────────────────────────────────────────────────────────
const COLORS = [
  "#7c3aed", "#6d28d9", "#5b21b6", "#4c1d95",
  "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe",
];

// ── tiny helpers ─────────────────────────────────────────────────────────────
function fmt(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}
function fmtMs(ms: number) {
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)}m`;
  if (ms >= 1_000) return `${(ms / 1_000).toFixed(1)}s`;
  return `${ms}ms`;
}
function fmtUsd(n: number) {
  if (n === 0) return "$0";
  if (n < 0.0001) return `$${n.toExponential(2)}`;
  return `$${n.toFixed(4)}`;
}

// ── DEMO SEED (shown when no query-api) ─────────────────────────────────────
const DEMO_TOOLS: ToolRow[] = [
  { tool: "browser.fetch",  invocations: 4820, errors: 182, total_duration_ms: 9_640_000 },
  { tool: "code.execute",   invocations: 3100, errors: 62,  total_duration_ms: 6_200_000 },
  { tool: "search.web",     invocations: 2670, errors: 40,  total_duration_ms: 3_338_000 },
  { tool: "file.read",      invocations: 1930, errors: 12,  total_duration_ms: 193_000   },
  { tool: "db.query",       invocations: 1420, errors: 99,  total_duration_ms: 2_840_000 },
  { tool: "email.send",     invocations:  840, errors: 21,  total_duration_ms: 252_000   },
  { tool: "pdf.parse",      invocations:  620, errors: 8,   total_duration_ms: 992_000   },
  { tool: "calendar.write", invocations:  310, errors: 3,   total_duration_ms: 93_000    },
];

const DEMO_AGENT: AgentCostRow[] = [
  { agent: "browser.fetch", llm_model: "openai/gpt-4o",      prompt_version: "v1", cost_usd_total: 1.24, tokens_in_total: 31000, tokens_out_total: 12000, call_count: 120 },
  { agent: "browser.fetch", llm_model: "openai/gpt-4o-mini", prompt_version: "v1", cost_usd_total: 0.18, tokens_in_total: 90000, tokens_out_total: 36000, call_count: 360 },
  { agent: "browser.fetch", llm_model: "openai/gpt-4o",      prompt_version: "v2", cost_usd_total: 0.93, tokens_in_total: 23000, tokens_out_total: 9000,  call_count:  90 },
  { agent: "code.execute",  llm_model: "openai/gpt-4o",      prompt_version: "v1", cost_usd_total: 0.87, tokens_in_total: 21000, tokens_out_total: 8000,  call_count:  82 },
  { agent: "code.execute",  llm_model: "anthropic/claude-3",  prompt_version: "v2", cost_usd_total: 0.62, tokens_in_total: 15000, tokens_out_total: 6000,  call_count:  60 },
  { agent: "search.web",    llm_model: "openai/gpt-4o-mini", prompt_version: "v1", cost_usd_total: 0.41, tokens_in_total: 20000, tokens_out_total: 8000,  call_count:  82 },
  { agent: "search.web",    llm_model: "openai/gpt-4o-mini", prompt_version: "v2", cost_usd_total: 0.28, tokens_in_total: 14000, tokens_out_total: 5000,  call_count:  56 },
  { agent: "db.query",      llm_model: "openai/gpt-4o",      prompt_version: "v1", cost_usd_total: 0.55, tokens_in_total: 14000, tokens_out_total: 5000,  call_count:  54 },
  { agent: "db.query",      llm_model: "openai/gpt-4o",      prompt_version: "v2", cost_usd_total: 0.31, tokens_in_total: 8000,  tokens_out_total: 3000,  call_count:  30 },
  { agent: "file.read",     llm_model: "openai/gpt-4o-mini", prompt_version: "v1", cost_usd_total: 0.09, tokens_in_total: 46000, tokens_out_total: 18000, call_count: 184 },
];

// ── heatmap builder ──────────────────────────────────────────────────────────
function buildHeatmap(rows: AgentCostRow[]) {
  const tools = [...new Set(rows.map((r) => r.agent))];
  const versions = [...new Set(rows.map((r) => r.prompt_version ?? "—"))].sort();
  const max = Math.max(...rows.map((r) => r.cost_usd_total), 0.0001);
  const lookup: Record<string, Record<string, number>> = {};
  for (const r of rows) {
    const v = r.prompt_version ?? "—";
    if (!lookup[r.agent]) lookup[r.agent] = {};
    lookup[r.agent][v] = (lookup[r.agent][v] ?? 0) + r.cost_usd_total;
  }
  return { tools, versions, lookup, max };
}

// ── custom tooltip ────────────────────────────────────────────────────────────
function LeaderboardTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as ToolRow;
  const errRate = d.invocations > 0 ? ((d.errors / d.invocations) * 100).toFixed(1) : "0.0";
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-xs space-y-1">
      <p className="font-medium text-white">{d.tool}</p>
      <p className="text-zinc-400">Invocations: <span className="text-white">{fmt(d.invocations)}</span></p>
      <p className="text-zinc-400">Errors: <span className="text-red-400">{fmt(d.errors)} ({errRate}%)</span></p>
      <p className="text-zinc-400">Avg duration: <span className="text-white">{fmtMs(Math.round(d.total_duration_ms / (d.invocations || 1)))}</span></p>
    </div>
  );
}

// ── page ─────────────────────────────────────────────────────────────────────
export default function ToolsPage() {
  const [since, setSince] = React.useState("7d");

  const { data: toolData, error: toolErr, isLoading: toolLoading } =
    useSWR(`tools-by-tool-${since}`, () => api.analytics.byTool(since), {
      onError: () => {},
      shouldRetryOnError: false,
    });

  const { data: agentData, error: agentErr, isLoading: agentLoading } =
    useSWR(`tools-by-agent-${since}`, () => api.analytics.byAgent(since), {
      onError: () => {},
      shouldRetryOnError: false,
    });

  const isDemo = !!(toolErr || agentErr);
  const tools: ToolRow[] = toolData?.items?.length ? toolData.items : isDemo ? DEMO_TOOLS : [];
  const agentRows: AgentCostRow[] = agentData?.items?.length ? agentData.items : isDemo ? DEMO_AGENT : [];

  const leaderboard = [...tools].sort((a, b) => b.invocations - a.invocations).slice(0, 10);
  const { tools: heatTools, versions, lookup, max } = buildHeatmap(agentRows);

  return (
    <div className="p-8 space-y-10 max-w-6xl mx-auto">
      {/* header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Tools</h1>
          <p className="text-sm text-zinc-500 mt-1">Cost leaderboard · Heatmap tool × prompt version</p>
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
                  : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
              )}
            >
              {w}
            </button>
          ))}
        </div>
      </div>

      {isDemo && (
        <div className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded px-3 py-2">
          Query API offline — showing demo data. Start the query-api to see live metrics.
        </div>
      )}

      {/* leaderboard */}
      <section>
        <h2 className="text-sm font-semibold text-zinc-300 mb-4 uppercase tracking-wider">
          Invocation leaderboard (top 10)
        </h2>
        {toolLoading && !isDemo ? (
          <div className="h-64 flex items-center justify-center text-zinc-500 text-sm">Loading…</div>
        ) : leaderboard.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-zinc-500 text-sm border border-dashed border-zinc-800 rounded-lg">
            No tool data for this window
          </div>
        ) : (
          <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart
                data={leaderboard}
                layout="vertical"
                margin={{ top: 0, right: 60, left: 110, bottom: 0 }}
              >
                <XAxis
                  type="number"
                  tickFormatter={fmt}
                  tick={{ fill: "#71717a", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="tool"
                  width={100}
                  tick={{ fill: "#a1a1aa", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<LeaderboardTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar dataKey="invocations" radius={[0, 4, 4, 0]} maxBarSize={22}>
                  {leaderboard.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>

            {/* error rate row */}
            <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
              {leaderboard.slice(0, 4).map((t) => {
                const rate = t.invocations > 0 ? (t.errors / t.invocations) * 100 : 0;
                return (
                  <div key={t.tool} className="bg-zinc-800/60 rounded-lg px-3 py-2">
                    <p className="text-xs text-zinc-400 truncate">{t.tool}</p>
                    <p className="text-base font-semibold text-white mt-0.5">{fmt(t.invocations)}</p>
                    <p className={clsx("text-xs mt-0.5", rate > 5 ? "text-red-400" : "text-zinc-500")}>
                      {rate.toFixed(1)}% err · {fmtMs(Math.round(t.total_duration_ms / (t.invocations || 1)))} avg
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* heatmap */}
      <section>
        <h2 className="text-sm font-semibold text-zinc-300 mb-4 uppercase tracking-wider">
          Cost heatmap — tool × prompt version
        </h2>
        {agentLoading && !isDemo ? (
          <div className="h-48 flex items-center justify-center text-zinc-500 text-sm">Loading…</div>
        ) : heatTools.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-zinc-500 text-sm border border-dashed border-zinc-800 rounded-lg">
            No cost data for this window
          </div>
        ) : (
          <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800 overflow-x-auto">
            <table className="text-xs w-full border-separate border-spacing-1">
              <thead>
                <tr>
                  <th className="text-left text-zinc-500 font-medium pr-4 pb-2 whitespace-nowrap">Tool / Agent</th>
                  {versions.map((v) => (
                    <th key={v} className="text-center text-zinc-400 font-medium pb-2 px-2 whitespace-nowrap">
                      {v}
                    </th>
                  ))}
                  <th className="text-right text-zinc-500 font-medium pl-4 pb-2">Total</th>
                </tr>
              </thead>
              <tbody>
                {heatTools.map((tool) => {
                  const rowTotal = Object.values(lookup[tool] ?? {}).reduce((a, b) => a + b, 0);
                  return (
                    <tr key={tool}>
                      <td className="text-zinc-300 pr-4 py-1 font-medium whitespace-nowrap">{tool}</td>
                      {versions.map((v) => {
                        const val = lookup[tool]?.[v] ?? 0;
                        const intensity = max > 0 ? val / max : 0;
                        return (
                          <td key={v} className="text-center py-1 px-1">
                            <div
                              title={`${tool} × ${v}: ${fmtUsd(val)}`}
                              className="rounded mx-auto flex items-center justify-center h-8 min-w-[48px] px-2 text-xs font-medium transition-all"
                              style={{
                                backgroundColor: val > 0
                                  ? `rgba(124,58,237,${0.15 + intensity * 0.85})`
                                  : "rgba(255,255,255,0.03)",
                                color: intensity > 0.4 ? "#fff" : intensity > 0 ? "#c4b5fd" : "#3f3f46",
                              }}
                            >
                              {val > 0 ? fmtUsd(val) : "—"}
                            </div>
                          </td>
                        );
                      })}
                      <td className="text-right text-zinc-300 pl-4 py-1 font-semibold whitespace-nowrap">
                        {fmtUsd(rowTotal)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td className="text-zinc-500 pr-4 pt-2 text-xs">Total</td>
                  {versions.map((v) => {
                    const colTotal = heatTools.reduce((s, t) => s + (lookup[t]?.[v] ?? 0), 0);
                    return (
                      <td key={v} className="text-center text-zinc-400 font-semibold pt-2 px-1">
                        {fmtUsd(colTotal)}
                      </td>
                    );
                  })}
                  <td className="text-right text-white font-semibold pt-2 pl-4">
                    {fmtUsd(heatTools.reduce((s, t) => s + Object.values(lookup[t] ?? {}).reduce((a, b) => a + b, 0), 0))}
                  </td>
                </tr>
              </tfoot>
            </table>

            <p className="text-xs text-zinc-600 mt-3">
              Darker cell = higher LLM cost driven by that agent × prompt version combination.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}

// React is needed for useState — add import
import React from "react";

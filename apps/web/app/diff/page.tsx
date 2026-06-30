"use client";

import React, { useState } from "react";
import clsx from "clsx";
import { api, type DiffResult, type RunSummary } from "../../lib/api";

// ── formatters ────────────────────────────────────────────────────────────────
function fmtUsd(n: number) {
  if (n === 0) return "$0.0000";
  return `$${Math.abs(n).toFixed(4)}`;
}
function fmtMs(ms: number) {
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)}m`;
  if (ms >= 1_000)  return `${(ms / 1_000).toFixed(1)}s`;
  return `${ms}ms`;
}
function fmtNum(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

// ── delta badge ───────────────────────────────────────────────────────────────
function Delta({ value, fmt, lowerIsBetter = false }: {
  value: number;
  fmt: (n: number) => string;
  lowerIsBetter?: boolean;
}) {
  if (value === 0) return <span className="text-zinc-500">no change</span>;
  const isImprovement = lowerIsBetter ? value < 0 : value > 0;
  return (
    <span className={clsx("font-semibold", isImprovement ? "text-green-400" : "text-red-400")}>
      {value > 0 ? "+" : "−"}{fmt(Math.abs(value))}
    </span>
  );
}

// ── metric row ────────────────────────────────────────────────────────────────
function MetricRow({ label, a, b, delta, fmt, lowerIsBetter, unit }: {
  label: string;
  a: number;
  b: number;
  delta: number;
  fmt: (n: number) => string;
  lowerIsBetter?: boolean;
  unit?: string;
}) {
  const pct = a !== 0 ? ((delta / a) * 100).toFixed(1) : null;
  return (
    <tr className="border-b border-zinc-800/60 last:border-0">
      <td className="px-5 py-3 text-sm text-zinc-400">{label}{unit ? <span className="text-zinc-600 ml-1 text-xs">{unit}</span> : null}</td>
      <td className="px-5 py-3 text-sm text-right text-zinc-200 font-mono">{fmt(a)}</td>
      <td className="px-5 py-3 text-sm text-right text-zinc-200 font-mono">{fmt(b)}</td>
      <td className="px-5 py-3 text-sm text-right font-mono">
        <Delta value={delta} fmt={fmt} lowerIsBetter={lowerIsBetter} />
        {pct && (
          <span className="text-zinc-600 text-xs ml-1">({pct}%)</span>
        )}
      </td>
    </tr>
  );
}

// ── demo result ───────────────────────────────────────────────────────────────
const DEMO: DiffResult = {
  run_a: "run-abc123",
  run_b: "run-def456",
  dimension: null,
  diff: {
    cost_usd:     { a: 0.0184, b: 0.0312, delta:  0.0128 },
    tokens_in:    { a:   4200, b:   7100, delta:   2900  },
    duration_ms:  { a:   8400, b:  11200, delta:   2800  },
    error_count:  { a:      0, b:      2 },
    events_count: { a:     14, b:     21 },
  },
};

// ── run input ─────────────────────────────────────────────────────────────────
function RunInput({ label, value, onChange }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex-1">
      <label className="block text-xs text-zinc-500 mb-1 font-medium uppercase tracking-wider">{label}</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="run_id…"
        className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-violet-500 font-mono"
      />
    </div>
  );
}

// ── page ──────────────────────────────────────────────────────────────────────
export default function DiffPage() {
  const [runA, setRunA] = useState("");
  const [runB, setRunB] = useState("");
  const [result, setResult] = useState<DiffResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState<string | null>(null);
  const [isDemo, setIsDemo] = useState(false);

  async function handleCompare() {
    if (!runA.trim() || !runB.trim()) return;
    setLoading(true);
    setError(null);
    setIsDemo(false);
    try {
      const data = await api.runs.compare(runA.trim(), runB.trim());
      setResult(data);
    } catch (e: any) {
      setError(e?.message || "Failed to compare runs");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  function loadDemo() {
    setRunA(DEMO.run_a);
    setRunB(DEMO.run_b);
    setResult(DEMO);
    setIsDemo(true);
    setError(null);
  }

  const d = result?.diff;

  return (
    <div className="p-8 space-y-8 max-w-4xl mx-auto">
      {/* header */}
      <div>
        <h1 className="text-2xl font-semibold">Diff / Compare</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Compare two runs side-by-side — cost, tokens, latency, errors
        </p>
      </div>

      {/* inputs */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
        <div className="flex gap-4 items-end">
          <RunInput label="Run A (baseline)" value={runA} onChange={setRunA} />
          <div className="pb-2 text-zinc-600 text-lg select-none">vs</div>
          <RunInput label="Run B (candidate)" value={runB} onChange={setRunB} />
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleCompare}
            disabled={loading || !runA.trim() || !runB.trim()}
            className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
          >
            {loading ? "Comparing…" : "Compare"}
          </button>
          <button
            onClick={loadDemo}
            className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-sm font-medium rounded-lg transition-colors"
          >
            Load demo
          </button>
        </div>
        {error && (
          <p className="text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded px-3 py-2">
            {error}
          </p>
        )}
      </div>

      {/* result */}
      {result && d && (
        <>
          {isDemo && (
            <div className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded px-3 py-2">
              Demo data — enter real run IDs and click Compare to see live results.
            </div>
          )}

          {/* run ids */}
          <div className="grid grid-cols-2 gap-4">
            {[
              { tag: "A", id: result.run_a, label: "Baseline" },
              { tag: "B", id: result.run_b, label: "Candidate" },
            ].map(({ tag, id, label }) => (
              <div key={tag} className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 flex items-center gap-3">
                <span className="text-xs font-bold bg-violet-700 text-white rounded px-2 py-0.5">{tag}</span>
                <div>
                  <p className="text-xs text-zinc-500">{label}</p>
                  <p className="text-sm font-mono text-zinc-200 truncate">{id}</p>
                </div>
                <a
                  href={`/runs/${id}`}
                  className="ml-auto text-xs text-violet-400 hover:text-violet-300 shrink-0"
                >
                  View →
                </a>
              </div>
            ))}
          </div>

          {/* summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Events A", value: fmtNum(d.events_count.a) },
              { label: "Events B", value: fmtNum(d.events_count.b) },
              {
                label: "Errors A",
                value: String(d.error_count.a),
                color: d.error_count.a > 0 ? "text-red-400" : "text-green-400",
              },
              {
                label: "Errors B",
                value: String(d.error_count.b),
                color: d.error_count.b > 0 ? "text-red-400" : "text-green-400",
              },
            ].map((c) => (
              <div key={c.label} className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
                <p className="text-xs text-zinc-500 mb-1">{c.label}</p>
                <p className={clsx("text-xl font-semibold", c.color ?? "text-white")}>{c.value}</p>
              </div>
            ))}
          </div>

          {/* metric table */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-800 text-xs text-zinc-500 uppercase tracking-wider">
                  <th className="text-left px-5 py-3 font-medium">Metric</th>
                  <th className="text-right px-5 py-3 font-medium">
                    <span className="bg-violet-900/50 text-violet-300 rounded px-1.5 py-0.5">A</span> Baseline
                  </th>
                  <th className="text-right px-5 py-3 font-medium">
                    <span className="bg-violet-700/50 text-violet-200 rounded px-1.5 py-0.5">B</span> Candidate
                  </th>
                  <th className="text-right px-5 py-3 font-medium">Delta</th>
                </tr>
              </thead>
              <tbody>
                <MetricRow
                  label="Cost"       unit="USD"
                  a={d.cost_usd.a}   b={d.cost_usd.b}   delta={d.cost_usd.delta}
                  fmt={fmtUsd}       lowerIsBetter
                />
                <MetricRow
                  label="Tokens in"
                  a={d.tokens_in.a}  b={d.tokens_in.b}  delta={d.tokens_in.delta}
                  fmt={fmtNum}       lowerIsBetter
                />
                <MetricRow
                  label="Duration"   unit="total"
                  a={d.duration_ms.a} b={d.duration_ms.b} delta={d.duration_ms.delta}
                  fmt={fmtMs}        lowerIsBetter
                />
              </tbody>
            </table>
          </div>

          {/* verdict */}
          {(() => {
            const worse = d.cost_usd.delta > 0 || d.tokens_in.delta > 0 || d.error_count.b > d.error_count.a;
            const better = d.cost_usd.delta < 0 && d.tokens_in.delta <= 0 && d.error_count.b <= d.error_count.a;
            return (
              <div className={clsx(
                "rounded-xl px-5 py-4 border text-sm font-medium",
                better ? "bg-green-900/20 border-green-700/40 text-green-300"
                       : worse ? "bg-red-900/20 border-red-700/40 text-red-300"
                                : "bg-zinc-800/60 border-zinc-700/40 text-zinc-300",
              )}>
                {better
                  ? "✓ Run B is cheaper and has fewer or equal errors — candidate looks good."
                  : worse
                  ? "✗ Run B is more expensive or has more errors than baseline — investigate before shipping."
                  : "~ Mixed results — review each metric individually."}
              </div>
            );
          })()}
        </>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";
import { api, ReplaySessionOut, ReplayStepResult } from "@/lib/api";
import { downloadJson } from "./CopyButton";

interface Props {
  runId: string;
}

interface StepRecord {
  step: number;
  state_hash: string;
  diverged: boolean;
  diff?: ReplayStepResult["diff"];
  state?: ReplayStepResult["state"];
  at: string;
}

export function ReplayStepper({ runId }: Props) {
  const [session, setSession] = useState<ReplaySessionOut | null>(null);
  const [history, setHistory] = useState<StepRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showState, setShowState] = useState(false);

  async function start() {
    setBusy(true);
    setError(null);
    setHistory([]);
    try {
      const s = await api.replay.start(runId);
      setSession(s);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  async function step(n = 1) {
    if (!session) return;
    setBusy(true);
    try {
      const res = await api.replay.step(session.session_id, n);
      setHistory((h) => [
        ...h,
        {
          step: res.step,
          state_hash: res.state_hash,
          diverged: res.diverged,
          diff: res.diff ?? null,
          state: res.state ?? null,
          at: new Date().toISOString(),
        },
      ]);
      const s = await api.replay.status(session.session_id);
      setSession(s);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  async function reset(to = 0) {
    if (!session) return;
    setBusy(true);
    try {
      await api.replay.reset(session.session_id, to);
      setHistory((h) => h.filter((r) => r.step <= to));
      const s = await api.replay.status(session.session_id);
      setSession(s);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runAll() {
    if (!session) return;
    setBusy(true);
    try {
      const s = await api.replay.run(session.session_id);
      setSession(s);
      if (s.last_state_hash) {
        setHistory((h) => [
          ...h,
          { step: s.current_step, state_hash: s.last_state_hash!, diverged: s.diverged_at != null, state: s.state ?? null, at: new Date().toISOString() },
        ]);
      }
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(target: string, value: boolean | string) {
    if (!session) return;
    setBusy(true);
    try {
      const s = await api.replay.toggle(session.session_id, target, value);
      setSession(s);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!session) {
    return (
      <div className="border border-zinc-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">Replay</h3>
        <p className="text-xs text-zinc-500 mb-3">Deterministic replay via checkpoints. Mock LLM and tools to match the original output.</p>
        <button
          onClick={start}
          disabled={busy}
          className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-sm rounded disabled:opacity-50"
        >
          {busy ? "Starting…" : "Start replay"}
        </button>
        {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
      </div>
    );
  }

  const lastDivergence = history.find((r) => r.diverged) ?? (session.diverged_at != null ? { step: session.diverged_at, state_hash: "—", diverged: true, at: "—" } : null);

  return (
    <div className="border border-zinc-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Replay · {session.status}</h3>
        <span className="text-xs text-zinc-500">
          step <span className="text-zinc-200 font-mono">{session.current_step}</span>/{session.total_steps}
        </span>
      </div>

      <dl className="text-xs space-y-0.5 bg-zinc-900 rounded p-2">
        <div className="flex justify-between"><dt className="text-zinc-500">session_id</dt><dd className="font-mono text-zinc-300 truncate max-w-[14rem]">{session.session_id}</dd></div>
        <div className="flex justify-between"><dt className="text-zinc-500">last_state_hash</dt><dd className="font-mono text-violet-300 truncate max-w-[14rem]">{session.last_state_hash ?? history.at(-1)?.state_hash ?? "—"}</dd></div>
        <div className="flex justify-between"><dt className="text-zinc-500">mock_llm</dt><dd>{session.mock_llm ? "yes" : "no"}</dd></div>
        <div className="flex justify-between"><dt className="text-zinc-500">mock_tools</dt><dd className="text-right">{session.mock_tools.length === 0 ? "none" : session.mock_tools.join(", ")}</dd></div>
      </dl>

      {lastDivergence && (
        <div className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded p-2 space-y-1">
          <div>Diverged at step <span className="font-mono">{lastDivergence.step}</span></div>
          {(lastDivergence as StepRecord).diff && (lastDivergence as StepRecord).diff!.length > 0 && (
            <ul className="list-disc pl-4 text-amber-200/80">
              {((lastDivergence as StepRecord).diff ?? []).map((d, i) => (
                <li key={i}>
                  <span className="font-mono">{d.field}</span>: expected <span className="font-mono">{JSON.stringify(d.expected)}</span>, got <span className="font-mono">{JSON.stringify(d.actual)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button onClick={() => step(1)} disabled={busy} className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded">Step</button>
        <button onClick={() => step(5)} disabled={busy} className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded">Step ×5</button>
        <button onClick={() => reset(0)} disabled={busy} className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded">Reset</button>
        <button onClick={runAll} disabled={busy} className="px-2 py-1 text-xs bg-emerald-700 hover:bg-emerald-600 text-white rounded">Run all</button>
        <button
          onClick={() => downloadJson(`${runId}-replay-${session.session_id}.json`, { session, history })}
          className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded ml-auto"
        >
          Download session
        </button>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={session.mock_llm} onChange={(e) => toggle("llm", e.target.checked)} />
          mock LLM
        </label>
        {["search", "browser.fetch", "calculator"].map((t) => (
          <label key={t} className="flex items-center gap-1.5">
            <input type="checkbox" checked={session.mock_tools.includes(t)} onChange={(e) => toggle("tool", e.target.checked ? t : "")} />
            {t}
          </label>
        ))}
      </div>

      {history.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <h4 className="text-xs font-semibold text-zinc-400">Step history · {history.length}</h4>
            <button onClick={() => setShowState((v) => !v)} className="text-[10px] text-zinc-500 hover:text-zinc-300">
              {showState ? "hide state" : "show state"}
            </button>
          </div>
          <ol className="text-[11px] font-mono space-y-1 max-h-48 overflow-y-auto">
            {history.map((r) => (
              <li key={`${r.step}-${r.at}`} className={`rounded px-2 py-1 ${r.diverged ? "bg-amber-950/30 border border-amber-800/40" : "bg-zinc-900"}`}>
                <div className="flex justify-between gap-2">
                  <span className="text-zinc-500">step {r.step}</span>
                  <span className="text-violet-300 truncate">{r.state_hash}</span>
                </div>
                {r.diverged && <div className="text-amber-300 text-[10px]">diverged</div>}
                {showState && r.state && (
                  <pre className="text-[10px] text-zinc-400 mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap break-all">
{JSON.stringify(r.state, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
    </div>
  );
}
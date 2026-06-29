"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { ReplaySessionOut } from "@/lib/api";

interface Props {
  runId: string;
}

export function ReplayStepper({ runId }: Props) {
  const [session, setSession] = useState<ReplaySessionOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true);
    setError(null);
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
      await api.replay.step(session.session_id, n);
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

  return (
    <div className="border border-zinc-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">Replay · {session.status}</h3>
        <span className="text-xs text-zinc-500">step {session.current_step}/{session.total_steps}</span>
      </div>
      {session.diverged_at != null && (
        <div className="mb-3 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded p-2">
          Diverged at step {session.diverged_at}
        </div>
      )}
      <div className="flex flex-wrap gap-2 mb-3">
        <button onClick={() => step(1)} disabled={busy} className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded">Step</button>
        <button onClick={() => step(5)} disabled={busy} className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded">Step ×5</button>
        <button onClick={() => reset(0)} disabled={busy} className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded">Reset</button>
        <button onClick={runAll} disabled={busy} className="px-2 py-1 text-xs bg-emerald-700 hover:bg-emerald-600 text-white rounded">Run all</button>
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
      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
    </div>
  );
}

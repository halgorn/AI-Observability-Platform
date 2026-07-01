"use client";

import { Checkpoint } from "@/lib/api";

interface Props {
  checkpoints: Checkpoint[];
  runId: string;
}

export function CheckpointsList({ checkpoints, runId }: Props) {
  const sorted = [...checkpoints].sort((a, b) => (a.step ?? 0) - (b.step ?? 0));
  if (sorted.length === 0) {
    return (
      <div className="space-y-2">
        <h2 className="text-lg font-semibold">Checkpoints</h2>
        <div className="text-zinc-500 text-sm border border-zinc-800 rounded-lg p-4">
          No checkpoints were emitted for this run.
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-4">
        <h2 className="text-lg font-semibold">Checkpoints</h2>
        <span className="text-sm text-zinc-500">{sorted.length} checkpoints</span>
      </div>
      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-zinc-900 text-zinc-400 uppercase tracking-wide">
            <tr>
              <th className="text-right px-3 py-2">step</th>
              <th className="text-left px-3 py-2">state_hash</th>
              <th className="text-right px-3 py-2">size</th>
              <th className="text-left px-3 py-2">thread_id</th>
              <th className="text-left px-3 py-2">saved_at</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((cp, i) => (
              <tr key={`${cp.step ?? i}-${cp.state_hash ?? ""}`} className="border-t border-zinc-800">
                <td className="px-3 py-1.5 text-right tabular-nums">{cp.step ?? "—"}</td>
                <td className="px-3 py-1.5 font-mono text-violet-300 truncate max-w-[20rem]">
                  {cp.state_hash ?? "—"}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">{cp.state_size ?? "—"}</td>
                <td className="px-3 py-1.5 font-mono text-zinc-500">{cp.thread_id ?? "—"}</td>
                <td className="px-3 py-1.5 text-zinc-500 font-mono">
                  {cp.saved_at ? new Date(cp.saved_at).toISOString() : cp.created_at ? new Date(cp.created_at).toISOString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-zinc-600">
        Full checkpoint state lives in the <span className="font-mono">checkpoints</span> table (FK <span className="font-mono">run_id</span>).
        The event payload only stores <span className="font-mono">state_hash</span> + size to keep events small.
      </p>
    </div>
  );
}
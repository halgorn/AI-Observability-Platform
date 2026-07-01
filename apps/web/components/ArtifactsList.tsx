"use client";

import { useState } from "react";
import { ArtifactRef, api } from "@/lib/api";
import { CopyButton } from "./CopyButton";

interface Props {
  artifacts: ArtifactRef[];
  runId: string;
}

export function ArtifactsList({ artifacts, runId }: Props) {
  const [openRef, setOpenRef] = useState<string | null>(null);
  const [content, setContent] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function open(ref: string) {
    setOpenRef(ref);
    setContent(null);
    setError(null);
    setLoading(true);
    try {
      const data = await api.runs.artifact(ref);
      if (data == null) {
        setError("No /v1/artifacts/{ref} endpoint reachable from query-api. Artifact blob is in object storage.");
      } else {
        setContent(data);
      }
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  if (artifacts.length === 0) {
    return (
      <div className="space-y-2">
        <h2 className="text-lg font-semibold">Artifacts</h2>
        <div className="text-zinc-500 text-sm border border-zinc-800 rounded-lg p-4">
          No artifact references on this run. LLM messages and tool I/O payloads go to object storage and are only linked via <span className="font-mono">attributes.artifact_ref</span> when emitted.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-4">
        <h2 className="text-lg font-semibold">Artifacts</h2>
        <span className="text-sm text-zinc-500">{artifacts.length} references</span>
      </div>
      <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800">
        {artifacts.map((a) => (
          <div key={a.ref} className="p-3 space-y-2">
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 font-mono">{a.source_type}</span>
              <span className="text-sm text-zinc-200 font-mono truncate">{a.context}</span>
              <span className="text-[10px] text-zinc-600 ml-auto font-mono">via {a.source_event.slice(0, 8)}…</span>
            </div>
            <div className="flex items-center gap-2">
              <code className="text-xs text-violet-300 font-mono truncate flex-1">{a.ref}</code>
              <CopyButton value={a.ref} label="Copy ref" />
              <button
                onClick={() => open(a.ref)}
                className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded"
              >
                {openRef === a.ref && loading ? "Loading…" : "Open"}
              </button>
            </div>
            {openRef === a.ref && (
              <div className="bg-zinc-950 rounded p-2 text-xs font-mono text-zinc-200 whitespace-pre-wrap break-words max-h-80 overflow-y-auto">
                {error ? (
                  <span className="text-amber-400">{error}</span>
                ) : content == null ? (
                  <span className="text-zinc-500">empty</span>
                ) : (
                  typeof content === "string" ? content : JSON.stringify(content, null, 2)
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
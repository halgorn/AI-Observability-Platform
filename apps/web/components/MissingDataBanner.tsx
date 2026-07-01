"use client";

import Link from "next/link";

interface Props {
  hasLLMCalls: boolean;
  hasToolInvocations: boolean;
  hasMessages: boolean;
  hasCheckpoints: boolean;
  totalEvents: number;
  runId: string;
}

export function MissingDataBanner({ hasLLMCalls, hasToolInvocations, hasMessages, hasCheckpoints, totalEvents, runId }: Props) {
  const missing: { label: string; reason: string }[] = [];
  if (!hasLLMCalls) missing.push({ label: "llm.call events", reason: "no model invocation was recorded for this run" });
  if (!hasToolInvocations) missing.push({ label: "tool.invoke events", reason: "no tool calls were recorded" });
  if (!hasLLMCalls && !hasToolInvocations && !hasMessages) {
    missing.push({ label: "raw messages / prompts", reason: "messages live in artifacts; without llm.call there is no artifact_ref" });
  }
  if (!hasCheckpoints) missing.push({ label: "checkpoints", reason: "replay state snapshots were not emitted; replay will fail" });

  if (missing.length === 0) return null;

  return (
    <div className="mb-6 border border-amber-800/60 bg-amber-950/20 rounded-lg p-4">
      <p className="text-xs font-semibold text-amber-300 mb-1">
        Sparse trace · {missing.length} item{missing.length > 1 ? "s" : ""} absent
      </p>
      <ul className="text-xs text-amber-200/90 space-y-1 list-disc pl-4">
        {missing.map((m) => (
          <li key={m.label}>
            <span className="font-mono">{m.label}</span> — <span className="text-amber-300/70">{m.reason}</span>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-zinc-500 mt-2">
        Total events in trace: <span className="font-mono">{totalEvents}</span>. See the schema in{" "}
        <Link href="https://github.com/anomalyco/AI-Observability-Platform/blob/main/specs/02-event-schema.md" className="text-violet-400 hover:underline">
          specs/02-event-schema.md
        </Link>{" "}
        for what each <span className="font-mono">type</span> is supposed to carry.
      </p>
    </div>
  );
}
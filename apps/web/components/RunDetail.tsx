"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  api, ApiError, Checkpoint, RunSummary, Trace, TraceEvent, TraceNode,
  collectArtifactRefs, findCausalPath,
} from "@/lib/api";
import { TraceView } from "@/components/TraceView";
import { ReplayStepper } from "@/components/ReplayStepper";
import { StatusBadge, formatCost, formatDuration } from "@/components/RunsList";
import { EventsTable } from "@/components/EventsTable";
import { CheckpointsList } from "@/components/CheckpointsList";
import { ArtifactsList } from "@/components/ArtifactsList";
import { MissingDataBanner } from "@/components/MissingDataBanner";
import { CopyButton, downloadJson } from "@/components/CopyButton";

type Tab = "trace" | "events" | "checkpoints" | "artifacts";

export function RunDetail({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunSummary | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedSpan, setSelectedSpan] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("trace");

  useEffect(() => {
    Promise.all([
      api.runs.get(runId),
      api.runs.trace(runId),
      api.runs.events(runId).then((r) => r.items as TraceEvent[]).catch(() => [] as TraceEvent[]),
      api.runs.checkpoints(runId).then((r) => r.items).catch(() => [] as Checkpoint[]),
    ])
      .then(([r, t, ev, cp]) => {
        setRun(r);
        setTrace(t);
        setEvents(ev);
        setCheckpoints(cp);
        if (t.summary?.error_span_id) setSelectedSpan(t.summary.error_span_id);
      })
      .catch((e) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
  }, [runId]);

  const artifacts = useMemo(() => collectArtifactRefs(events), [events]);

  if (error)
    return (
      <div className="p-8 text-red-400">
        <p className="font-semibold">Failed to load run</p>
        <p className="text-sm text-zinc-500 mt-2">{error}</p>
      </div>
    );
  if (!run || !trace) return <div className="p-8 text-zinc-500">Loading…</div>;

  const s = trace.summary;
  const selectedNode = selectedSpan ? findNode(trace.roots, selectedSpan) : null;
  const causalPath = selectedSpan ? findCausalPath(trace.roots, selectedSpan) : [];
  const spanLink = typeof window !== "undefined" ? `${window.location.origin}/runs/${runId}#span=${selectedSpan ?? ""}` : `/runs/${runId}#span=${selectedSpan ?? ""}`;

  return (
    <div className="p-8 space-y-6">
      <header className="space-y-3">
        <div className="flex items-baseline gap-4 flex-wrap">
          <Link href="/runs" className="text-sm text-zinc-500 hover:text-zinc-300">← runs</Link>
          <h1 className="text-lg font-mono break-all">{run.run_id}</h1>
          <StatusBadge status={run.status} />
          <span className="text-sm text-zinc-400">{run.agent}</span>
          <span className="text-sm text-zinc-500 ml-auto tabular-nums">
            {formatDuration(run.duration_ms)} · {formatCost(run.total_cost_usd)} · {run.total_steps ?? "—"} steps
          </span>
        </div>
        <RunMetaBar summary={s} runId={runId} />
      </header>

      <MissingDataBanner
        hasLLMCalls={!!s.has_llm_calls}
        hasToolInvocations={!!s.has_tool_invocations}
        hasMessages={!!s.has_messages}
        hasCheckpoints={!!s.has_checkpoints}
        totalEvents={s.total_events}
        runId={runId}
      />

      {run.status === "failed" && (
        <div className="border border-red-800 bg-red-950/30 rounded-lg p-4">
          <div className="flex items-baseline gap-2 mb-1">
            <p className="text-xs font-semibold text-red-400">
              {trace.summary?.error_type ?? "Run failed"}
            </p>
            {s.error_span_id && (
              <button
                onClick={() => { setSelectedSpan(s.error_span_id!); setTab("trace"); }}
                className="text-[11px] text-red-300 hover:text-red-200 underline ml-auto"
              >
                jump to causal span ({s.error_span_id.slice(0, 8)}…)
              </button>
            )}
          </div>
          {trace.summary?.error_message ? (
            <p className="text-sm text-red-300 font-mono break-words">{trace.summary.error_message}</p>
          ) : (
            <p className="text-xs text-zinc-500">No error message captured. Inspect error spans below.</p>
          )}
        </div>
      )}

      <nav className="flex items-center gap-1 border-b border-zinc-800">
        <TabBtn active={tab === "trace"} onClick={() => setTab("trace")}>Trace</TabBtn>
        <TabBtn active={tab === "events"} onClick={() => setTab("events")}>Events · {events.length}</TabBtn>
        <TabBtn active={tab === "checkpoints"} onClick={() => setTab("checkpoints")}>Checkpoints · {checkpoints.length}</TabBtn>
        <TabBtn active={tab === "artifacts"} onClick={() => setTab("artifacts")}>Artifacts · {artifacts.length}</TabBtn>
      </nav>

      {tab === "trace" && (
        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2">
            <TraceView roots={trace.roots} summary={trace.summary} selectedId={selectedSpan} onSelect={setSelectedSpan} />
          </div>
          <div className="space-y-4">
            {selectedNode && <SpanDetail node={selectedNode} causalPath={causalPath} />}
            <ReplayStepper runId={runId} />
          </div>
        </div>
      )}

      {tab === "events" && (
        <EventsTable events={events} runId={runId} onSelect={(id) => { setSelectedSpan(id); setTab("trace"); }} />
      )}

      {tab === "checkpoints" && <CheckpointsList checkpoints={checkpoints} runId={runId} />}

      {tab === "artifacts" && <ArtifactsList artifacts={artifacts} runId={runId} />}
    </div>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 text-sm border-b-2 -mb-px ${
        active ? "border-violet-500 text-violet-200" : "border-transparent text-zinc-400 hover:text-zinc-200"
      }`}
    >
      {children}
    </button>
  );
}

function RunMetaBar({ summary, runId }: { summary: Trace["summary"]; runId: string }) {
  const items: { label: string; value: React.ReactNode; copy?: string }[] = [
    { label: "input_hash", value: shortHash(summary.input_hash), copy: summary.input_hash ?? undefined },
    { label: "output_hash", value: shortHash(summary.output_hash), copy: summary.output_hash ?? undefined },
    { label: "prompt_version", value: summary.prompt_version ?? "—" },
    { label: "thread_id", value: summary.thread_id ?? "—" },
    {
      label: "parent_run_id",
      value: summary.parent_run_id ? (
        <Link href={`/runs/${summary.parent_run_id}`} className="text-violet-300 hover:underline font-mono">
          {summary.parent_run_id.slice(0, 8)}…
        </Link>
      ) : "—",
    },
  ];

  return (
    <div className="border border-zinc-800 rounded-lg p-3 flex flex-wrap gap-x-6 gap-y-2 text-xs">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-1.5 min-w-0">
          <span className="text-zinc-500">{it.label}</span>
          <span className="text-zinc-200 font-mono truncate max-w-[16rem]">{it.value}</span>
          {it.copy && <CopyButton value={it.copy} label="copy" className="px-1 py-0.5 text-[10px] bg-zinc-800 hover:bg-zinc-700 rounded" />}
        </div>
      ))}
      {summary.tags && summary.tags.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap min-w-0">
          <span className="text-zinc-500">tags</span>
          {summary.tags.map((t) => (
            <span key={t} className="px-1.5 py-0.5 bg-zinc-800 text-zinc-300 rounded font-mono">{t}</span>
          ))}
        </div>
      )}
      <div className="ml-auto flex gap-2">
        <CopyButton value={runId} label="Copy run_id" />
        <button
          onClick={() => downloadJson(`${runId}-trace.json`, summary)}
          className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded"
        >
          Export summary
        </button>
      </div>
    </div>
  );
}

function shortHash(h: string | null | undefined): React.ReactNode {
  if (!h) return "—";
  if (h.length <= 16) return h;
  return <span title={h}>{h.slice(0, 10)}…{h.slice(-6)}</span>;
}

function findNode(roots: Trace["roots"], spanId: string): Trace["roots"][number] | null {
  for (const r of roots) {
    if (r.span_id === spanId) return r;
    const found = findNode(r.children, spanId);
    if (found) return found;
  }
  return null;
}

function SpanDetail({ node, causalPath }: { node: TraceNode; causalPath: TraceNode[] }) {
  const ev = node.event;
  const payload = (ev?.payload ?? {}) as Record<string, unknown>;
  const attrs = (ev?.attributes ?? {}) as Record<string, unknown>;
  const [view, setView] = useState<"structured" | "raw">("structured");

  const spanUrl = typeof window !== "undefined" ? `${window.location.origin}/runs/${ev.run_id}#span=${node.span_id}` : "";

  return (
    <div className="border border-zinc-800 rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Span</h3>
        <div className="flex gap-1 text-[10px]">
          <button
            onClick={() => setView("structured")}
            className={`px-2 py-0.5 rounded ${view === "structured" ? "bg-violet-600 text-white" : "bg-zinc-800 text-zinc-400"}`}
          >
            structured
          </button>
          <button
            onClick={() => setView("raw")}
            className={`px-2 py-0.5 rounded ${view === "raw" ? "bg-violet-600 text-white" : "bg-zinc-800 text-zinc-400"}`}
          >
            raw
          </button>
        </div>
      </div>

      {view === "raw" ? (
        <pre className="bg-zinc-950 rounded p-2 text-[11px] font-mono text-zinc-200 overflow-x-auto max-h-[28rem] overflow-y-auto">
{JSON.stringify(ev, null, 2)}
        </pre>
      ) : (
        <>
          <dl className="text-xs space-y-1">
            <Row label="name">{node.name}</Row>
            <Row label="kind">{node.kind}</Row>
            <Row label="status">
              <span className={node.status === "error" ? "text-red-400" : "text-emerald-400"}>{node.status}</span>
            </Row>
            <Row label="duration">{formatDuration(node.duration_ms)}</Row>
            <Row label="started">{ev.started_at ? new Date(ev.started_at).toISOString() : "—"}</Row>
            {ev.ended_at && <Row label="ended">{new Date(ev.ended_at).toISOString()}</Row>}
            {ev.agent && <Row label="agent"><span className="font-mono">{ev.agent}</span></Row>}
            {ev.tool && <Row label="tool"><span className="font-mono">{ev.tool}</span></Row>}
            {ev.llm_model && <Row label="model"><span className="font-mono">{ev.llm_model}</span></Row>}
            {ev.tokens_in != null && <Row label="tokens_in">{ev.tokens_in}</Row>}
            {ev.tokens_out != null && <Row label="tokens_out">{ev.tokens_out}</Row>}
            {ev.cost_usd != null && <Row label="cost">{formatCost(ev.cost_usd)}</Row>}
            {ev.error_code && <Row label="error_code"><span className="text-red-400 font-mono">{ev.error_code}</span></Row>}
          </dl>

          {node.kind === "llm" && <LLMBlock ev={ev} />}
          {node.kind === "tool" && <ToolBlock ev={ev} />}
          {node.kind === "handoff" && <HandoffBlock ev={ev} />}
          {node.kind === "checkpoint" && <CheckpointBlock ev={ev} />}
          {node.kind === "error" && <ErrorBlock ev={ev} causalPath={causalPath} />}

          <PayloadBlock payload={payload} />
          <AttributesBlock attrs={attrs} />
        </>
      )}

      <div className="flex items-center justify-between pt-2 border-t border-zinc-800">
        <span className="text-[10px] text-zinc-600 font-mono">{node.span_id}</span>
        <div className="flex gap-1">
          <CopyButton value={node.span_id} label="Copy id" />
          {spanUrl && <CopyButton value={spanUrl} label="Copy link" />}
          <CopyButton value={JSON.stringify(ev, null, 2)} label="Copy JSON" />
        </div>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-zinc-500 shrink-0">{label}</dt>
      <dd className="text-right break-all">{children}</dd>
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-zinc-800/60 rounded p-2 space-y-1 bg-zinc-950/40">
      <h4 className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{title}</h4>
      {children}
    </div>
  );
}

function LLMBlock({ ev }: { ev: TraceEvent }) {
  const p = (ev.payload ?? {}) as Record<string, any>;
  const a = (ev.attributes ?? {}) as Record<string, any>;
  return (
    <Block title="llm.call">
      <Row label="finish_reason"><span className="font-mono">{p.finish_reason ?? "—"}</span></Row>
      <Row label="system_prompt_version"><span className="font-mono">{p.system_prompt_version ?? "—"}</span></Row>
      <Row label="messages_hash">
        <span className="font-mono text-violet-300 break-all">{p.messages_hash ?? "—"}</span>
      </Row>
      <Row label="messages_size">{p.messages_size ?? "—"}</Row>
      <Row label="artifact_ref">
        <ArtifactRefRow ref={a.artifact_ref ?? p.artifact_ref} />
      </Row>
      <p className="text-[10px] text-zinc-500 mt-2">
        Message content (system / user / assistant turns) is <strong>not</strong> stored in the event — it lives in object storage and is linked via <span className="font-mono">artifact_ref</span>.
      </p>
    </Block>
  );
}

function ToolBlock({ ev }: { ev: TraceEvent }) {
  const p = (ev.payload ?? {}) as Record<string, any>;
  const a = (ev.attributes ?? {}) as Record<string, any>;
  return (
    <Block title="tool.invoke">
      <Row label="args_hash"><span className="font-mono text-violet-300 break-all">{p.args_hash ?? "—"}</span></Row>
      <Row label="result_hash"><span className="font-mono text-violet-300 break-all">{p.result_hash ?? "—"}</span></Row>
      <Row label="result_size">{p.result_size ?? "—"}</Row>
      <Row label="cache_hit">
        {p.cache_hit === true ? <span className="text-emerald-400">true</span> : p.cache_hit === false ? <span className="text-zinc-400">false</span> : "—"}
      </Row>
      <Row label="retry_count">{p.retry_count ?? 0}</Row>
      <Row label="artifact_ref"><ArtifactRefRow ref={a.artifact_ref ?? p.artifact_ref} /></Row>
      <p className="text-[10px] text-zinc-500 mt-2">
        Tool argument and result bodies are not in the event — use <span className="font-mono">artifact_ref</span> to fetch them.
      </p>
    </Block>
  );
}

function HandoffBlock({ ev }: { ev: TraceEvent }) {
  const p = (ev.payload ?? {}) as Record<string, any>;
  return (
    <Block title="handoff">
      <Row label="from">{p.from ?? "—"}</Row>
      <Row label="to">{p.to ?? "—"}</Row>
      <Row label="reason"><span className="font-mono">{p.reason ?? "—"}</span></Row>
      <Row label="payload_hash"><span className="font-mono text-violet-300 break-all">{p.payload_hash ?? "—"}</span></Row>
    </Block>
  );
}

function CheckpointBlock({ ev }: { ev: TraceEvent }) {
  const p = (ev.payload ?? {}) as Record<string, any>;
  return (
    <Block title="checkpoint">
      <Row label="step">{p.step ?? "—"}</Row>
      <Row label="state_hash"><span className="font-mono text-violet-300 break-all">{p.state_hash ?? "—"}</span></Row>
      <Row label="state_size">{p.state_size ?? "—"}</Row>
      <p className="text-[10px] text-zinc-500 mt-2">
        State body is stored in the <span className="font-mono">checkpoints</span> table, not in the event.
      </p>
    </Block>
  );
}

function ErrorBlock({ ev, causalPath }: { ev: TraceEvent; causalPath: TraceNode[] }) {
  const p = (ev.payload ?? {}) as Record<string, any>;
  const a = (ev.attributes ?? {}) as Record<string, any>;
  const msg = (a["error.message"] ?? p.message ?? "") as string;
  const type = (a["error.type"] ?? p.code ?? "") as string;
  const stack = (a["error.stack"] ?? p.stack ?? "") as string;
  const retryable = p.retryable;
  return (
    <Block title="error">
      <Row label="error_code"><span className="text-red-400 font-mono">{ev.error_code ?? p.code ?? "—"}</span></Row>
      <Row label="error.type"><span className="font-mono text-red-300">{type || "—"}</span></Row>
      <div className="bg-red-950/40 rounded p-2 text-xs font-mono text-red-200 break-words whitespace-pre-wrap">
        {msg || <span className="text-zinc-500">no message</span>}
      </div>
      {typeof retryable === "boolean" && <Row label="retryable">{retryable ? "yes" : "no"}</Row>}
      {stack && (
        <details className="mt-2">
          <summary className="text-[10px] text-zinc-500 cursor-pointer hover:text-zinc-300">stack (redacted)</summary>
          <pre className="bg-zinc-950 rounded p-2 mt-1 text-[10px] font-mono text-zinc-400 max-h-40 overflow-y-auto whitespace-pre-wrap">{stack}</pre>
        </details>
      )}
      {causalPath.length > 1 && (
        <div className="mt-3 pt-2 border-t border-zinc-800">
          <p className="text-[10px] text-zinc-500 mb-1">Causal path:</p>
          <ol className="text-[11px] space-y-0.5 font-mono">
            {causalPath.map((n, i) => (
              <li key={n.span_id} className={i === causalPath.length - 1 ? "text-red-300" : "text-zinc-400"}>
                {i > 0 && <span className="text-zinc-600">↳ </span>}
                <span className="text-zinc-500">{n.kind}</span> · {n.name}
              </li>
            ))}
          </ol>
        </div>
      )}
    </Block>
  );
}

function ArtifactRefRow({ ref }: { ref?: string }) {
  if (!ref) return <span className="text-zinc-500">—</span>;
  return (
    <div className="flex items-center gap-1 justify-end">
      <span className="font-mono text-violet-300 break-all text-right max-w-[14rem]">{ref}</span>
      <CopyButton value={ref} label="copy" className="px-1 py-0.5 text-[10px] bg-zinc-800 hover:bg-zinc-700 rounded" />
    </div>
  );
}

function PayloadBlock({ payload }: { payload: Record<string, unknown> }) {
  const rows = Object.entries(payload).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (rows.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-zinc-400 mb-1">Payload</h4>
      <div className="bg-zinc-900 rounded p-2 text-xs font-mono space-y-0.5">
        {rows.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <span className="text-zinc-500 shrink-0">{k}</span>
            <span className="text-zinc-200 break-words">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AttributesBlock({ attrs }: { attrs: Record<string, unknown> }) {
  const skip = new Set([
    "event_type", "genai.agent.name", "genai.tool.name", "genai.llm.model",
    "error.message", "error.type", "error.stack", "artifact_ref",
  ]);
  const rows = Object.entries(attrs).filter(([k, v]) =>
    v !== null && v !== undefined && v !== "" && !skip.has(k)
  );
  if (rows.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-zinc-400 mb-1">Attributes</h4>
      <div className="bg-zinc-900 rounded p-2 text-xs font-mono space-y-0.5 max-h-40 overflow-y-auto">
        {rows.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <span className="text-zinc-500 shrink-0 truncate max-w-[40%]">{k}</span>
            <span className="text-zinc-200 break-words">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
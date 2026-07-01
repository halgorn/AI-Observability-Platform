import Link from "next/link";

export default function Home() {
  return (
    <div className="p-8 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-3">AI Observability Platform</h1>
      <p className="text-zinc-400 mb-6">
        Event-sourced observability for LLM agents. Trace every step, attribute cost per tool, replay deterministically.
      </p>
      <div className="grid grid-cols-3 gap-3">
        <Link href="/runs" className="block p-4 border border-zinc-800 rounded-lg hover:border-violet-500 transition-colors">
          <div className="text-sm font-semibold mb-1">Runs</div>
          <div className="text-xs text-zinc-500">Browse, search, drill into trace</div>
        </Link>
        <Link href="/agents" className="block p-4 border border-zinc-800 rounded-lg hover:border-violet-500 transition-colors">
          <div className="text-sm font-semibold mb-1">Agents</div>
          <div className="text-xs text-zinc-500">Handoff graph + success rate</div>
        </Link>
        <Link href="/tools" className="block p-4 border border-zinc-800 rounded-lg hover:border-violet-500 transition-colors">
          <div className="text-sm font-semibold mb-1">Tools</div>
          <div className="text-xs text-zinc-500">Cost leaderboard + heatmap</div>
        </Link>
      </div>
    </div>
  );
}

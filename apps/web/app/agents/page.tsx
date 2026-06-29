export default function AgentsPage() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-2">Agents</h1>
      <p className="text-sm text-zinc-500 mb-6">Handoff graph per agent. Click an agent to drill into its runs.</p>
      <div className="border border-dashed border-zinc-800 rounded-lg p-12 text-center text-zinc-500 text-sm">
        Handoff graph view — implement with React Flow (PRD §10 marco 9-10).
        For now, browse <a href="/runs" className="text-violet-400 hover:underline">runs</a> by agent.
      </div>
    </div>
  );
}

export default function ToolsPage() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold mb-2">Tools</h1>
      <p className="text-sm text-zinc-500 mb-6">Cost leaderboard by tool. Heatmap tool × prompt version.</p>
      <div className="border border-dashed border-zinc-800 rounded-lg p-12 text-center text-zinc-500 text-sm">
        Cost leaderboard — implement with Recharts (PRD §10 marco 9-10).
        For now, browse <a href="/runs" className="text-violet-400 hover:underline">runs</a> to see tool calls.
      </div>
    </div>
  );
}

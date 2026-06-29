import { RunsList } from "@/components/RunsList";

export default function RunsPage() {
  return (
    <div>
      <header className="px-8 pt-8 pb-2">
        <h1 className="text-2xl font-semibold">Runs</h1>
        <p className="text-sm text-zinc-500">Recent agent executions. Click a run to inspect the trace and replay it.</p>
      </header>
      <RunsList />
    </div>
  );
}

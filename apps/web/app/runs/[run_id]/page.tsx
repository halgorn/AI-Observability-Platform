import { RunDetail } from "@/components/RunDetail";

export default function RunPage({ params }: { params: { run_id: string } }) {
  return <RunDetail runId={params.run_id} />;
}

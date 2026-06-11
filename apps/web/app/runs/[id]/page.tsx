import { LiveRun } from "./LiveRun";

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <LiveRun runId={Number(id)} />;
}

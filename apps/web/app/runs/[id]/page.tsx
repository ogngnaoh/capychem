import type { Metadata } from "next";
import { LiveRun } from "./LiveRun";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  return { title: `Run ${id} — CapyChem` };
}

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <LiveRun runId={Number(id)} />;
}

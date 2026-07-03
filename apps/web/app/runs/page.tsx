import type { Metadata } from "next";
import { RunsBrowse } from "./RunsBrowse";

export const metadata: Metadata = { title: "Runs — CapyChem" };

export default function RunsPage() {
  return <RunsBrowse />;
}

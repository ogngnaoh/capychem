import type { Metadata } from "next";
import { Launcher } from "./Launcher";

export const metadata: Metadata = { title: "Launch a run — CapyChem" };

export default function LaunchPage() {
  return <Launcher />;
}

import type { Metadata } from "next";
import { Overview } from "./Overview";

export const metadata: Metadata = { title: "CapyChem — Overview" };

export default function Home() {
  return <Overview />;
}

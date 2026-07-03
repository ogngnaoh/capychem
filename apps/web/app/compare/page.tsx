import type { Metadata } from "next";
import { CompareView } from "./CompareView";

export const metadata: Metadata = { title: "Compare runs — CapyChem" };

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>;
}) {
  const { a, b } = await searchParams;
  return <CompareView a={Number(a)} b={Number(b)} />;
}

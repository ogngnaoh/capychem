// LOW-FI PROTOTYPE — Compare stub. This surface largely exists at /compare
// (overlaid AUC curves: coral = A, chart-2 = B; side-by-side top-K; per-run stats).
// Re-skinned onto the shell in slice 03; not a hero surface for this slice, so it
// is stubbed here only to complete the Overview · Workbench · Runs · Compare IA.
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";

export default function CompareProtoStub() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-heading text-2xl font-normal">Compare</h1>
      <Card>
        <CardContent className="flex flex-col gap-2 py-5 text-sm text-muted-foreground">
          <p>
            Compare two runs — overlaid AUC curves (coral = A, chart-2 = B),
            side-by-side top molecules, and per-run oracle-call and cost stats.
          </p>
          <p>
            This surface already exists at{" "}
            <Link href="/compare" className="underline underline-offset-2">
              /compare
            </Link>{" "}
            and is re-skinned onto this shell in slice 03 — not a hero layout for the
            low-fi pass.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

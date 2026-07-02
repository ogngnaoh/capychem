// LOW-FI PROTOTYPE — Runs (browse) stub. This surface largely exists at /runs
// (a dense scannable table with a status filter). In the redesign it is re-skinned
// onto the shell + tokens; its layout is not a hero surface for this slice, so it
// is stubbed here only to complete the Overview · Workbench · Runs · Compare IA.
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";

export default function RunsProtoStub() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-heading text-2xl font-normal">Runs</h1>
      <Card>
        <CardContent className="flex flex-col gap-2 py-5 text-sm text-muted-foreground">
          <p>
            Browse all runs — a dense, scannable table filterable by status, sortable
            by best score / oracle calls / time.
          </p>
          <p>
            This surface already exists at{" "}
            <Link href="/runs" className="underline underline-offset-2">
              /runs
            </Link>{" "}
            and is re-skinned onto this shell in slice 03 — not a hero layout for the
            low-fi pass.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

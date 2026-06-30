import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnalyzerHypothesis } from "@/lib/api";

function Chips({ structured }: { structured: AnalyzerHypothesis["structured_json"] }) {
  if (!structured) return null;
  const focus = structured.focus;
  const avoid = structured.avoid ?? [];
  if (!focus && avoid.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {focus && <Badge variant="secondary">focus: {focus}</Badge>}
      {avoid.map((a, i) => (
        <Badge key={`${i}-${a}`} variant="outline">
          avoid: {a}
        </Badge>
      ))}
    </div>
  );
}

function Entry({ h, latest }: { h: AnalyzerHypothesis; latest: boolean }) {
  return (
    <details open={latest} className="rounded-md border px-3 py-2">
      <summary className="cursor-pointer text-sm font-medium">
        After gen {h.after_generation_index}
        {latest && <span className="ml-2 text-xs text-muted-foreground">· latest</span>}
      </summary>
      <p className="mt-2 text-sm text-zinc-700">{h.text}</p>
      <Chips structured={h.structured_json} />
    </details>
  );
}

export function HypothesisSection({ hypotheses }: { hypotheses: AnalyzerHypothesis[] }) {
  if (hypotheses.length === 0) return null;
  const ordered = [...hypotheses].sort(
    (a, b) => b.after_generation_index - a.after_generation_index,
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Analyzer reasoning</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {ordered.map((h, i) => (
          <Entry key={h.after_generation_index} h={h} latest={i === 0} />
        ))}
      </CardContent>
    </Card>
  );
}

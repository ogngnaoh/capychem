"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createRun } from "@/lib/api";

const DEFAULTS = {
  budget: 200,
  seed: 42,
  pop_size: 100,
  offspring: 32,
  mutation_rate: 0.01,
  plateau_window: 5,
  max_generations: 100,
};

export default function Home() {
  const router = useRouter();
  const [form, setForm] = useState(DEFAULTS);
  const [strategy, setStrategy] = useState<"graph_ga" | "llm">("graph_ga");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const num =
    (k: keyof typeof DEFAULTS) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [k]: Number(e.target.value) });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (form.budget <= 0) return setError("Budget must be a positive integer.");
    if (form.pop_size <= 1) return setError("Population size must be greater than 1.");
    setBusy(true);
    try {
      const { run_id } = await createRun({
        task: "jnk3",
        mutation_strategy: strategy,
        ...form,
      });
      router.push(`/runs/${run_id}`);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-6 p-8">
      <Card>
        <CardHeader>
          <CardTitle>Launch a jnk3 optimization</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="grid grid-cols-2 gap-4">
            {(
              [
                ["budget", "Oracle-call budget"],
                ["seed", "Seed"],
                ["pop_size", "Population size"],
                ["offspring", "Offspring / gen"],
                ["mutation_rate", "Mutation rate"],
                ["plateau_window", "Plateau window"],
                ["max_generations", "Max generations"],
              ] as const
            ).map(([k, label]) => (
              <div key={k} className="flex flex-col gap-1">
                <Label htmlFor={k}>{label}</Label>
                <Input
                  id={k}
                  type="number"
                  step="any"
                  value={form[k]}
                  onChange={num(k)}
                />
              </div>
            ))}
            <div className="flex flex-col gap-1">
              <Label htmlFor="mutation_strategy">Mutation strategy</Label>
              <select
                id="mutation_strategy"
                value={strategy}
                onChange={(e) =>
                  setStrategy(e.target.value as "graph_ga" | "llm")
                }
                className="h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="graph_ga">Graph-GA</option>
                <option value="llm">LLM proposer</option>
              </select>
            </div>
            <div className="col-span-2 flex items-center justify-between">
              {error && <span className="text-sm text-red-600">{error}</span>}
              <Button type="submit" disabled={busy} className="ml-auto">
                {busy ? "Starting…" : "Start run"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

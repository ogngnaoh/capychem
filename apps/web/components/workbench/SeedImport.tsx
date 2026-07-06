"use client";

// Rich seed-import (07-02, FR-001): a multi-line paste box + a .smi/.csv/.sdf file
// upload, both feeding one SMILES list. RDKit at POST /runs is the authoritative
// validator — this only tokenizes. A custom seed list marks the run exploratory.
// Controlled: the parent owns the raw text (so the launcher can parse + gate on it);
// file upload appends parsed SMILES into that text.

import { useRef, useState } from "react";
import { parseSeeds, parseSeedFile } from "./seedParse";

export function SeedImport({
  value,
  onChange,
  rejected = [],
}: {
  value: string;
  onChange: (text: string) => void;
  // SMILES the server rejected at launch (RDKit 422) — surfaced per-token.
  rejected?: string[];
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [note, setNote] = useState<string | null>(null);
  const [fileErr, setFileErr] = useState<string | null>(null);

  const parsed = parseSeeds(value);
  const rejectedSet = new Set(rejected);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    setFileErr(null);
    setNote(null);
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const { smiles, note: parseNote } = parseSeedFile(file.name, text);
      if (smiles.length === 0) {
        setFileErr(
          parseNote ??
            "No SMILES found in that file. Paste SMILES, or upload a .smi/.csv with one per line.",
        );
      } else {
        const merged = [...parsed, ...smiles];
        onChange(merged.join("\n"));
        setNote(parseNote ?? `Imported ${smiles.length} SMILES from ${file.name}.`);
      }
    } catch {
      setFileErr("Couldn't read that file.");
    } finally {
      // Allow re-selecting the same file.
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <textarea
        aria-label="Seed molecules"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        placeholder="default population — or paste SMILES (one per line, or space/comma separated)"
        className="w-full resize-y rounded-lg border border-input bg-background px-2.5 py-2 font-mono text-xs shadow-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      />
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          Upload file
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".smi,.csv,.sdf,.txt"
          aria-label="Upload seed file"
          onChange={onFile}
          className="hidden"
        />
        <span className="text-xs text-muted-foreground">
          {parsed.length > 0
            ? `${parsed.length} SMILES parsed`
            : ".smi / .csv (one per line) · .sdf (needs a <SMILES> tag)"}
        </span>
      </div>

      {note && <p className="text-xs text-muted-foreground">{note}</p>}
      {fileErr && (
        <p role="alert" className="text-xs text-destructive">
          {fileErr}
        </p>
      )}

      {parsed.length > 0 && (
        <ul className="flex max-h-28 flex-col gap-1 overflow-y-auto rounded-lg border border-border bg-muted/30 p-2">
          {parsed.map((s, i) => {
            const bad = rejectedSet.has(s);
            return (
              <li
                key={`${s}-${i}`}
                className="flex items-center justify-between gap-2 font-mono text-[0.7rem]"
              >
                <span className={`truncate ${bad ? "text-destructive" : "text-foreground"}`}>
                  {s}
                </span>
                <span
                  className={`shrink-0 text-[0.62rem] ${bad ? "text-destructive" : "text-muted-foreground"}`}
                >
                  {bad ? "rejected" : "accepted"}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-[0.7rem] leading-relaxed text-muted-foreground">
        RDKit-validated at launch. A custom list starts gen 0 from your compounds and marks
        the run <span className="font-medium">exploratory</span> (not benchmark-comparable);
        empty uses the standard population.
      </p>
    </div>
  );
}

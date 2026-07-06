// Pure client-side seed parsing (07-02). RDKit at POST /runs is the authoritative
// validator — this only splits text into candidate SMILES tokens for the paste box and
// file upload. Kept framework-free so it's unit tested directly.

// Split free-text (paste box) into SMILES on whitespace, commas, or newlines. A custom
// list marks the run exploratory server-side.
export function parseSeeds(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

// CSV / SMI: one molecule per line; take the first whitespace/comma token as the SMILES.
// A header row whose first token isn't a plausible SMILES is skipped.
export function parseSmiCsv(text: string): string[] {
  const out: string[] = [];
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const token = line.split(/[\s,\t]+/)[0]?.trim();
    if (!token) continue;
    // Skip an obvious header row (first line, no ring/bond chars, looks like a label).
    if (i === 0 && /^(smiles|structure|mol|compound|name|id)$/i.test(token)) continue;
    out.push(token);
  }
  return out;
}

// SDF is not fully parseable in-browser (no RDKit). Honest path: split records on
// `$$$$` and pull a `> <SMILES>` (or `> <smiles>`) property tag when present. Records
// without one are reported so the user knows to paste SMILES instead.
export type SdfParse = { smiles: string[]; recordsWithoutSmiles: number };

export function parseSdf(text: string): SdfParse {
  const records = text.split(/\$\$\$\$/).map((r) => r.trim()).filter(Boolean);
  const smiles: string[] = [];
  let missing = 0;
  for (const rec of records) {
    // Match `> <SMILES>` (case-insensitive) then the value on the next non-empty line.
    const m = rec.match(/^>\s*<\s*smiles\s*>[^\n]*\n\s*([^\n]+)/im);
    const value = m?.[1]?.trim();
    if (value) smiles.push(value);
    else missing += 1;
  }
  return { smiles, recordsWithoutSmiles: missing };
}

export type FileParse = {
  smiles: string[];
  note: string | null; // an honest caveat (e.g. SDF records without a SMILES tag)
};

// Dispatch by extension. `.sdf` uses the tag-extraction path; everything else is
// treated as line-oriented SMI/CSV.
export function parseSeedFile(filename: string, text: string): FileParse {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".sdf")) {
    const { smiles, recordsWithoutSmiles } = parseSdf(text);
    const note =
      recordsWithoutSmiles > 0
        ? `${recordsWithoutSmiles} SDF record${recordsWithoutSmiles === 1 ? "" : "s"} had no <SMILES> tag — SDF can't be fully parsed in-browser; paste SMILES for those.`
        : null;
    return { smiles, note };
  }
  return { smiles: parseSmiCsv(text), note: null };
}

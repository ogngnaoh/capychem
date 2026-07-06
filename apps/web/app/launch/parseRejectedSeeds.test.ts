import { describe, expect, it } from "vitest";
import { parseRejectedSeeds } from "./Launcher";

// A3: the /runs 422 for a bad seed names the offenders as a Python list repr; SeedImport
// marks exactly those tokens. Parsing must be faithful (never guess) and bracket-safe.
describe("parseRejectedSeeds", () => {
  it("extracts the SMILES the server named in a single-quoted list", () => {
    const msg =
      "Value error, Validate seed SMILES via RDKit; these did not parse: ['xyz', 'C1CC']";
    expect(parseRejectedSeeds(msg)).toEqual(["xyz", "C1CC"]);
  });

  it("does not truncate SMILES that contain brackets", () => {
    const msg = "these did not parse: ['c1cc[nH]c1BAD', 'O=[N+]([O-])x']";
    expect(parseRejectedSeeds(msg)).toEqual(["c1cc[nH]c1BAD", "O=[N+]([O-])x"]);
  });

  it("handles double-quoted tokens", () => {
    expect(parseRejectedSeeds('did not parse: ["O=C(", "foo"]')).toEqual(["O=C(", "foo"]);
  });

  it("returns [] when the message names no rejected SMILES", () => {
    expect(parseRejectedSeeds("HTTP 500")).toEqual([]);
    expect(parseRejectedSeeds("Budget must be positive")).toEqual([]);
  });
});

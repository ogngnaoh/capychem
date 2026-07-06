import { describe, expect, it } from "vitest";
import { parseSeedFile, parseSeeds, parseSdf, parseSmiCsv } from "./seedParse";

describe("parseSeeds (paste box)", () => {
  it("splits on whitespace, commas, and newlines", () => {
    expect(parseSeeds("CCO, CCN c1ccccc1\nCCC")).toEqual(["CCO", "CCN", "c1ccccc1", "CCC"]);
  });

  it("returns an empty list for blank input", () => {
    expect(parseSeeds("   \n  ")).toEqual([]);
  });
});

describe("parseSmiCsv", () => {
  it("takes the first token per line", () => {
    expect(parseSmiCsv("CCO 0.9\nc1ccccc1,arene")).toEqual(["CCO", "c1ccccc1"]);
  });

  it("skips an obvious header row", () => {
    expect(parseSmiCsv("smiles,name\nCCO,ethanol\nCCN,amine")).toEqual(["CCO", "CCN"]);
  });
});

describe("parseSdf", () => {
  it("extracts a <SMILES> tag when present", () => {
    const sdf = [
      "mol1",
      "  fake block",
      "M  END",
      "> <SMILES>",
      "CCO",
      "",
      "$$$$",
    ].join("\n");
    expect(parseSdf(sdf)).toEqual({ smiles: ["CCO"], recordsWithoutSmiles: 0 });
  });

  it("counts records without a SMILES tag honestly (no faked parsing)", () => {
    const sdf = "mol-without-tag\nM  END\n$$$$";
    expect(parseSdf(sdf)).toEqual({ smiles: [], recordsWithoutSmiles: 1 });
  });
});

describe("parseSeedFile", () => {
  it("dispatches .csv to the line parser", () => {
    expect(parseSeedFile("seeds.csv", "CCO\nCCN")).toEqual({ smiles: ["CCO", "CCN"], note: null });
  });

  it("dispatches .sdf and surfaces a caveat when a tag is missing", () => {
    const out = parseSeedFile("seeds.sdf", "mol\nM  END\n$$$$");
    expect(out.smiles).toEqual([]);
    expect(out.note).toMatch(/SDF/);
  });
});

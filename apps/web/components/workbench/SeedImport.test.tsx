import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SeedImport } from "./SeedImport";

// A3 / F2: the server (RDKit at POST /runs) is authoritative; when it 422s a seed, the
// launcher passes the named SMILES down as `rejected` and SeedImport marks exactly those.
describe("SeedImport rejected tokens", () => {
  it("marks the server-rejected SMILES and accepts the rest", () => {
    render(
      <SeedImport
        value={"CCO\nBADSMILES\nc1ccccc1"}
        onChange={() => {}}
        rejected={["BADSMILES"]}
      />,
    );
    expect(screen.getByText("rejected")).toBeInTheDocument();
    expect(screen.getAllByText("accepted")).toHaveLength(2);
  });

  it("marks every token accepted when nothing was rejected", () => {
    render(<SeedImport value={"CCO c1ccccc1"} onChange={() => {}} />);
    expect(screen.queryByText("rejected")).toBeNull();
    expect(screen.getAllByText("accepted")).toHaveLength(2);
  });
});

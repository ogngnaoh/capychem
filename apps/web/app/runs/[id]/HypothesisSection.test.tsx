import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { HypothesisSection } from "./HypothesisSection";
import type { AnalyzerHypothesis } from "@/lib/api";

const hyps: AnalyzerHypothesis[] = [
  { after_generation_index: 1, text: "early signal", structured_json: { focus: "aromatic", avoid: ["ester"] } },
  { after_generation_index: 2, text: "refine amide scaffold", structured_json: { focus: "amide", avoid: ["phenol", "nitro"] } },
];

describe("HypothesisSection", () => {
  it("renders nothing when there are no hypotheses", () => {
    const { container } = render(<HypothesisSection hypotheses={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
  it("renders newest first with prose, the latest marked, and focus/avoid chips", () => {
    render(<HypothesisSection hypotheses={hyps} />);
    expect(screen.getByText("refine amide scaffold")).toBeInTheDocument();
    expect(screen.getByText(/latest/i)).toBeInTheDocument();
    expect(screen.getByText("focus: amide")).toBeInTheDocument();
    expect(screen.getByText("avoid: phenol")).toBeInTheDocument();
    expect(screen.getByText("avoid: nitro")).toBeInTheDocument();
    // newest-first ordering: gen 2 heading appears before gen 1 in the DOM
    const headings = screen.getAllByText(/After gen \d/);
    expect(headings[0]).toHaveTextContent("After gen 2");
    expect(headings[1]).toHaveTextContent("After gen 1");
  });
});

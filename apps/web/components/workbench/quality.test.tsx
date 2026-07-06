import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PopulationHealth, QualityBadges } from "./quality";

describe("QualityBadges", () => {
  it("renders QED/SA and pass-fail chips from a full quality report", () => {
    render(
      <QualityBadges
        quality={{
          valid: true,
          qed: 0.83,
          sa_score: 2.41,
          lipinski_pass: true,
          veber_pass: false,
          pains: false,
          brenk: true,
        }}
      />,
    );
    expect(screen.getByText(/QED 0\.83/)).toBeInTheDocument();
    expect(screen.getByText(/SA 2\.41/)).toBeInTheDocument();
    expect(screen.getByText(/Lipinski ✓/)).toBeInTheDocument();
    expect(screen.getByText(/Veber ✕/)).toBeInTheDocument();
    // brenk flag = bad (shown); pains false (not shown)
    expect(screen.getByText(/Brenk ⚠/)).toBeInTheDocument();
    expect(screen.queryByText(/PAINS/)).toBeNull();
  });

  it("shows a computing chip while quality is null (live run)", () => {
    render(<QualityBadges quality={null} />);
    expect(screen.getByText(/computing/i)).toBeInTheDocument();
  });

  it("never crashes on a sparse quality dict (missing keys)", () => {
    render(<QualityBadges quality={{ valid: true, qed: 0.5 }} />);
    expect(screen.getByText(/QED 0\.50/)).toBeInTheDocument();
    expect(screen.queryByText(/Lipinski/)).toBeNull();
  });
});

describe("PopulationHealth", () => {
  it("renders diversity/novelty as percentages when present", () => {
    render(<PopulationHealth diversity={0.62} novelty={0.4} live={false} />);
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
  });

  it("shows computing… while live and — when null on a finished run", () => {
    const { rerender } = render(
      <PopulationHealth diversity={null} novelty={null} live={true} />,
    );
    expect(screen.getAllByText(/computing/i).length).toBeGreaterThan(0);
    rerender(<PopulationHealth diversity={null} novelty={null} live={false} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});

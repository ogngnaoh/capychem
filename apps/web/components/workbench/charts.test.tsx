import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

// recharts needs ResizeObserver (absent in jsdom); stub it so we test the panel chrome.
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  ReferenceLine: () => null,
}));

import { AucPanel } from "./charts";

// A1: with an empty curve there is no scored generation to compare, so a signed
// "behind/beating baseline by X" would be fabricated — the cold-start / reconnect window.
describe("AucPanel baseline honesty", () => {
  it("shows no signed baseline delta before the first generation", () => {
    render(<AucPanel curve={[]} baseline={0.77} running={true} />);
    expect(screen.queryByText(/Behind baseline/i)).toBeNull();
    expect(screen.queryByText(/Beating baseline/i)).toBeNull();
    expect(screen.getByText(/awaiting the first generation/i)).toBeInTheDocument();
  });

  it("shows the delta once the curve has at least one point", () => {
    render(
      <AucPanel
        curve={[{ oracle_calls: 100, top10_mean: 0.9 }]}
        baseline={0.77}
        running={true}
      />,
    );
    expect(screen.getByText(/Beating baseline/i)).toBeInTheDocument();
  });

  it("shows the no-baseline note when no baseline exists (regardless of curve)", () => {
    render(<AucPanel curve={[]} baseline={null} running={false} />);
    expect(screen.getByText(/no Graph-GA baseline/i)).toBeInTheDocument();
  });
});

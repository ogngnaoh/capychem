import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModeBadge } from "./ModeBadge";

describe("ModeBadge", () => {
  it("labels a benchmark run", () => {
    render(<ModeBadge mode="benchmark" />);
    expect(screen.getByText(/benchmark/i)).toBeInTheDocument();
  });

  it("labels an exploratory run as not benchmark-comparable", () => {
    render(<ModeBadge mode="exploratory" />);
    expect(screen.getByText(/not benchmark-comparable/i)).toBeInTheDocument();
  });

  it("does not paint the exploratory badge with the coral --primary token", () => {
    // The honesty signal must not read as the app's primary accent (handoff: 'don't
    // reuse the coral --primary'), so it isn't mistaken for a positive/branded state.
    const { container } = render(<ModeBadge mode="exploratory" />);
    const withPrimaryBg = container.querySelectorAll('[class*="bg-primary"]');
    expect(withPrimaryBg.length).toBe(0);
  });

  it("never emits the forbidden 21/23 collapse", () => {
    const { container } = render(<ModeBadge mode="benchmark" />);
    expect(container.textContent).not.toMatch(/21\/23/);
  });
});

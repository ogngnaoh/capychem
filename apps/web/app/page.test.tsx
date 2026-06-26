import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createRun = vi.fn().mockResolvedValue({ run_id: 7 });
vi.mock("@/lib/api", () => ({ createRun: (...a: unknown[]) => createRun(...a) }));

import Home from "./page";

describe("launch form (jnk3)", () => {
  beforeEach(() => {
    createRun.mockClear();
    push.mockClear();
  });

  it("renders a jnk3-targeted form with strategy + plateau fields", () => {
    render(<Home />);
    screen.getByText(/Launch a jnk3 optimization/i);
    screen.getByLabelText(/Mutation strategy/i);
    screen.getByLabelText(/Plateau window/i);
  });

  it("submits task=jnk3 with the chosen strategy + plateau_window", async () => {
    render(<Home />);
    fireEvent.change(screen.getByLabelText(/Oracle-call budget/i), {
      target: { value: "120" },
    });
    fireEvent.change(screen.getByLabelText(/Mutation strategy/i), {
      target: { value: "llm" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start run/i }));

    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        task: "jnk3",
        mutation_strategy: "llm",
        plateau_window: 5,
        budget: 120,
      }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/runs/7"));
  });
});

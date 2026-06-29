import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createRun = vi.fn().mockResolvedValue({ run_id: 7 });
vi.mock("@/lib/api", () => ({ createRun: (...a: unknown[]) => createRun(...a) }));

import Home from "./page";

describe("launch form", () => {
  beforeEach(() => {
    createRun.mockClear();
    push.mockClear();
  });

  it("renders the form with a task selector defaulting to jnk3", () => {
    render(<Home />);
    screen.getByText(/Launch an optimization/i);
    const select = screen.getByLabelText(/^Task$/i) as HTMLSelectElement;
    expect(select.value).toBe("jnk3");
    screen.getByLabelText(/Mutation strategy/i);
    screen.getByLabelText(/Plateau window/i);
  });

  it("submits the default task=jnk3 with the chosen strategy", async () => {
    render(<Home />);
    fireEvent.change(screen.getByLabelText(/Mutation strategy/i), {
      target: { value: "llm" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start run/i }));
    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({ task: "jnk3", mutation_strategy: "llm" }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/runs/7"));
  });

  it("submits the selected task when changed", async () => {
    render(<Home />);
    fireEvent.change(screen.getByLabelText(/^Task$/i), {
      target: { value: "drd2" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start run/i }));
    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({ task: "drd2" }),
    );
  });
});

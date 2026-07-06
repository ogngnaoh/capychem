import { act, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunSnapshot } from "@/lib/api";

const getRun = vi.fn();
const getManifest = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api", () => ({
  getRun: (...a: unknown[]) => getRun(...a),
  stopRun: vi.fn(),
  resumeRun: vi.fn(),
  wsUrl: (id: number) => `ws://test/ws/runs/${id}`,
  moleculeSvgUrl: (s: string) => `svg:${s}`,
  getManifest: (...a: unknown[]) => getManifest(...a),
  manifestUrl: (id: number) => `http://test/runs/${id}/manifest`,
  exportCsvUrl: (id: number) => `http://test/runs/${id}/export.csv`,
  exportSdfUrl: (id: number) => `http://test/runs/${id}/export.sdf`,
}));

// recharts needs ResizeObserver (absent in jsdom); stub it so we test the cockpit chrome.
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  ReferenceLine: () => null,
}));

import { LiveRun } from "./LiveRun";

function terminalSnap(over: Partial<RunSnapshot> = {}): RunSnapshot {
  return {
    run_id: 271,
    task: "qed",
    mode: "benchmark",
    status: "max_generations", // terminal → no WebSocket opened
    budget: 120,
    plateau_window: 5,
    generation_index: 8,
    oracle_calls_used: 80,
    best_score: 0.9455,
    top_k: [{ smiles: "CCO", score: 0.9455 }],
    auc_curve: [{ oracle_calls: 80, top10_mean: 0.94 }],
    cost_so_far_usd: 0.0149,
    hypotheses: [],
    ...over,
  };
}

describe("LiveRun trace link (FR-014)", () => {
  it("links out to the Langfuse trace when trace_url is present", async () => {
    getRun.mockResolvedValue(
      terminalSnap({ trace_url: "http://localhost:3001/project/p/traces/t" }),
    );
    render(<LiveRun runId={271} />);
    const link = await screen.findByRole("link", { name: /view trace/i });
    expect(link).toHaveAttribute("href", "http://localhost:3001/project/p/traces/t");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("shows no trace link when trace_url is absent", async () => {
    getRun.mockResolvedValue(terminalSnap({ trace_url: null }));
    render(<LiveRun runId={271} />);
    await screen.findByText(/Run 271/);
    expect(screen.queryByRole("link", { name: /view trace/i })).toBeNull();
  });
});

describe("Cockpit mode badge (07-01)", () => {
  it("badges a benchmark run", async () => {
    getRun.mockResolvedValue(terminalSnap({ mode: "benchmark" }));
    render(<LiveRun runId={271} />);
    await screen.findByText(/Run 271/);
    expect(screen.getByText(/^Benchmark$/)).toBeInTheDocument();
  });

  it("badges an exploratory run as not benchmark-comparable", async () => {
    getRun.mockResolvedValue(terminalSnap({ mode: "exploratory" }));
    render(<LiveRun runId={271} />);
    await screen.findByText(/Run 271/);
    expect(screen.getByText(/not benchmark-comparable/i)).toBeInTheDocument();
  });
});

// A controllable WebSocket double: the app opens it, and the test drives onopen/onclose.
class MockWS {
  static instances: MockWS[] = [];
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: ((e: Event) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  readyState = 0;
  url: string;
  constructor(url: string) {
    this.url = url;
    MockWS.instances.push(this);
  }
  close() {
    this.readyState = 3;
  }
}

function runningSnap(over: Partial<RunSnapshot> = {}): RunSnapshot {
  return {
    run_id: 284,
    task: "jnk3",
    mode: "benchmark",
    status: "running", // non-terminal → LiveRun opens the socket
    budget: 10000,
    plateau_window: 5,
    generation_index: 5,
    oracle_calls_used: 2000,
    best_score: 0.71,
    top_k: [{ smiles: "CCO", score: 0.71 }],
    auc_curve: [{ oracle_calls: 2000, top10_mean: 0.7 }],
    cost_so_far_usd: 0.4,
    hypotheses: [],
    ...over,
  };
}

describe("LiveRun WS resilience (07-08)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    MockWS.instances = [];
  });

  it("shows a distinct 'reconnecting…' state when the socket drops on a running run", async () => {
    vi.stubGlobal("WebSocket", MockWS);
    getRun.mockResolvedValue(runningSnap());
    render(<LiveRun runId={284} />);
    await screen.findByText(/Run 284/);
    await act(async () => {
      await Promise.resolve();
    });
    expect(MockWS.instances).toHaveLength(1);
    act(() => MockWS.instances[0].onopen?.(new Event("open")));
    // Socket drops while the run is still non-terminal → reconnecting, not "done".
    act(() => MockWS.instances[0].onclose?.(new Event("close")));
    // Rendered in both the header indicator and the banner.
    expect(screen.getAllByText(/reconnecting/i).length).toBeGreaterThan(0);
  });

  it("re-fetches the snapshot on auto-reconnect before resuming the stream (A2)", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", MockWS);
    getRun.mockReset().mockResolvedValue(runningSnap()); // fresh call history for this test
    render(<LiveRun runId={284} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0); // resolve getRun → first socket
    });
    expect(getRun).toHaveBeenCalledTimes(1);
    expect(MockWS.instances).toHaveLength(1);

    getRun.mockClear();
    // Drop the socket while the run is still non-terminal → schedules a reconnect.
    act(() => MockWS.instances[0].onopen?.(new Event("open")));
    act(() => MockWS.instances[0].onclose?.(new Event("close")));
    // Before the backoff fires: no re-fetch yet and no new socket (the stream is paused,
    // not resumed onto a stale snapshot).
    expect(getRun).not.toHaveBeenCalled();
    expect(MockWS.instances).toHaveLength(1);

    // The backoff timer (attempt 1 ≈ 1s) fires: reconnect re-fetches, THEN reopens.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(getRun).toHaveBeenCalledWith(284);
    expect(MockWS.instances).toHaveLength(2);
  });

  it("gives up after the backoff ladder and offers a manual retry that re-fetches", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", MockWS);
    getRun.mockResolvedValue(runningSnap());
    render(<LiveRun runId={284} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0); // resolve getRun → first socket
    });
    // Close each socket and let the backoff timer spawn the next, past MAX attempts.
    for (let i = 0; i < 7; i++) {
      const ws = MockWS.instances.at(-1)!;
      act(() => ws.onclose?.(new Event("close")));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(16_000); // > the 15s cap
      });
    }
    const retry = screen.getByRole("button", { name: /retry connection/i });
    expect(retry).toBeInTheDocument();
    getRun.mockClear();
    act(() => retry.click());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getRun).toHaveBeenCalledWith(284);
  });
});

describe("Cockpit surfacing (slice 03b)", () => {
  it("renders analyzer reasoning, the valid-SMILES vital, and the Graph-GA beating delta", async () => {
    getRun.mockResolvedValue(
      terminalSnap({
        graph_ga_baseline: 0.77,
        valid_smiles_rate: 0.93,
        hypotheses: [
          {
            after_generation_index: 3,
            text: "Fluorinated anilides held the top of the population.",
            structured_json: { focus: "para-F anilide", avoid: ["phenol"] },
          },
        ],
      }),
    );
    render(<LiveRun runId={271} />);
    await screen.findByText(/Analyzer reasoning/i);
    expect(
      screen.getByText("Fluorinated anilides held the top of the population."),
    ).toBeInTheDocument();
    expect(screen.getByText(/focus: para-F anilide/i)).toBeInTheDocument();
    expect(screen.getByText("93%")).toBeInTheDocument();
    // latest top-10 mean (0.94) beats the baseline (0.77)
    expect(screen.getByText(/Beating baseline/i)).toBeInTheDocument();
  });
});

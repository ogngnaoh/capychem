import { describe, expect, it } from "vitest";
import { plateauNotice } from "./plateau";

describe("plateauNotice", () => {
  it("returns a signal naming the window when status is plateaued", () => {
    const msg = plateauNotice("plateaued", 5);
    expect(msg).toContain("5");
    expect(msg).toMatch(/plateau/i);
  });
  it("returns null for non-plateaued statuses", () => {
    expect(plateauNotice("running", 5)).toBeNull();
    expect(plateauNotice("exhausted", 5)).toBeNull();
    expect(plateauNotice("stopped", 5)).toBeNull();
  });
});

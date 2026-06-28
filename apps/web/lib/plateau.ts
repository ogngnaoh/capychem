// Pure signal helper for the watch-live plateau callout (FR-003, Story 2).
// Returns the operator-facing message when a run stopped on plateau, else null.
export function plateauNotice(
  status: string,
  plateauWindow: number,
): string | null {
  if (status !== "plateaued") return null;
  return `Score plateaued — no improvement over ${plateauWindow} generations. Run stopped automatically.`;
}

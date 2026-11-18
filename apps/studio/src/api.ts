/** The live application never substitutes recorded data for a failed request. */
export const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
    /\/$/,
    "",
  ) || "/api";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort(init.signal?.reason);
  if (init.signal?.aborted) abort();
  else init.signal?.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(() => controller.abort(), 30_000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      let detail: unknown;
      try {
        const data = await response.json();
        detail = data.detail;
        message =
          typeof data.detail === "string"
            ? data.detail
            : typeof data.detail?.message === "string"
              ? data.detail.message
              : Array.isArray(data.detail)
                ? data.detail.map((e: { msg?: string }) => e.msg).join("; ")
                : data.message || message;
      } catch {
        /* status remains useful */
      }
      throw new ApiError(message, response.status, detail);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (controller.signal.aborted && !init.signal?.aborted)
      throw new ApiError(
        "The local engine did not respond in time. Check its connection and retry.",
        0,
      );
    throw error;
  } finally {
    clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abort);
  }
}
export function artifactUrl(path?: string): string | undefined {
  if (!path) return undefined;
  if (
    path.startsWith("http") ||
    path.startsWith("data:") ||
    path.startsWith("/data/")
  )
    return path;
  return path.startsWith("/api/")
    ? path
    : `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}

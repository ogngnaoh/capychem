import { useEffect, useRef, useState } from "react";
import { ApiError, request } from "./api";
import { loadRecordedManifest } from "./recordedData";
import { studyActive, type Study } from "./studyModel";

export function useStudies(demo: boolean, id?: string) {
  const [items, setItems] = useState<Study[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);
  const [revision, setRevision] = useState(0);
  const [pageCount, setPageCount] = useState(1);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const scope = useRef("");
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const key = `${demo}:${id ?? "index"}`;
    if (scope.current !== key) {
      scope.current = key;
      setItems([]);
      setLoading(true);
      setNextCursor(null);
    }
    setError("");
    setMissing(false);
    const refresh = async () => {
      try {
        let next: Study[];
        let cursor: string | null = null;
        if (demo) {
          const manifest = await loadRecordedManifest();
          next = (manifest?.studies ?? []).filter((s) => !id || s.id === id);
          if (id && !next.length)
            throw new ApiError(
              "This study is not included in the recorded example.",
              404,
            );
        } else if (id)
          next = [
            await request<Study>(`/studies/${encodeURIComponent(id)}`, {
              signal: abort.signal,
            }),
          ];
        else {
          next = [];
          for (let page = 0; page < pageCount; page++) {
            const result: { items: Study[]; next_cursor?: string | null } =
              await request(
                `/studies?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
                { signal: abort.signal },
              );
            next.push(...result.items);
            cursor = result.next_cursor ?? null;
            if (!cursor) break;
          }
        }
        if (abort.signal.aborted) return;
        setItems(next);
        setNextCursor(cursor);
        setError("");
        setLoading(false);
        setLoadingMore(false);
        if (!demo && (!id || next.some(studyActive)))
          timer = setTimeout(refresh, 3000);
      } catch (e) {
        if (abort.signal.aborted) return;
        setError(
          e instanceof Error ? e.message : "Studies could not be loaded.",
        );
        setMissing(e instanceof ApiError && e.status === 404);
        setLoading(false);
        setLoadingMore(false);
      }
    };
    void refresh();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [demo, id, revision, pageCount]);
  return {
    items,
    study: items[0],
    loading,
    error,
    missing,
    hasMore: !!nextCursor,
    loadingMore,
    loadMore: () => {
      if (nextCursor && !loadingMore) {
        setLoadingMore(true);
        setPageCount((n) => n + 1);
      }
    },
    refresh: () => setRevision((r) => r + 1),
  };
}

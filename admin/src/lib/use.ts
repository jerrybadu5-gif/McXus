import { useCallback, useEffect, useRef, useState } from "react";

/** Load data from the API; `reload` refetches. Keeps the old data while reloading. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const reload = useCallback(() => {
    const n = ++seq.current;
    setLoading(true);
    load().then(
      (d) => { if (n === seq.current) { setData(d); setError(undefined); setLoading(false); } },
      (e) => { if (n === seq.current) { setError(e); setLoading(false); } },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(reload, [reload]);
  return { data, error, loading, reload, setData };
}

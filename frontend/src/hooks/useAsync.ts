import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (value: T | undefined) => void;
}

/** Runs `fn` on mount and whenever `deps` change; results from stale calls are ignored. */
export function useAsync<T>(fn: () => Promise<T>, deps: readonly unknown[], enabled = true): AsyncState<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const seq = useRef(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    try {
      const value = await fnRef.current();
      if (id === seq.current) {
        setData(value);
        setError(null);
      }
    } catch (err) {
      if (id === seq.current) setError(err);
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (enabled) void reload();
    else setLoading(false);
  }, [enabled, reload, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps

  return { data, error, loading, reload, setData };
}

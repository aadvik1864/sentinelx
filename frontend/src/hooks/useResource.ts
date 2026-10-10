import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../services/api";

export function useResource<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    if (!path) {
      setLoading(false);
      setData(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    api
      .get<T>(path, { signal: controller.signal })
      .then(({ data: result }) => {
        setData(result);
        setLoadedPath(path);
        setError(null);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(errorMessage(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, revision]);
  useEffect(() => {
    const timer = window.setInterval(reload, 30000);
    window.addEventListener("sentinelx:refresh", reload);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("sentinelx:refresh", reload);
    };
  }, [reload]);
  return { data: loadedPath === path ? data : null, error, loading, reload };
}

export function useDebounced(value: string, delay = 300) {
  const [result, setResult] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setResult(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return result;
}

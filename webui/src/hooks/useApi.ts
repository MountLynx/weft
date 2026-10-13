/** GET 数据 hook：loading/error/data 三态 + 手动 reload（无全局缓存层，设计 D3）。 */
import {useCallback, useEffect, useState} from "react";
import {ApiError} from "../api/client";

export function useApi<T>(path: string | null): {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (path === null) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    fetch(path).then(async (resp) => {
      if (!resp.ok) {
        let payload: Record<string, unknown> = {};
        try {
          payload = await resp.json();
        } catch {
          /* 非 JSON 错误体 */
        }
        throw new ApiError(resp.status, payload);
      }
      return resp.json();
    }).then((body) => {
      if (!alive) return;
      setData(body as T);
      setError(null);
      setLoading(false);
    }).catch((err) => {
      if (!alive) return;
      setError(err instanceof ApiError ? err : new ApiError(0, {detail: String(err)}));
      setData(null);
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return {data, error, loading, reload};
}

/** GET 数据 hook：loading/error/data 三态 + 手动 reload（无全局缓存层，设计 D3）。
 * 路径切换在渲染期同步丢弃上一路径的数据（data 与 path 严格同帧，杜绝跨路径脏渲染）；
 * 同路径 reload 保留旧数据免闪。 */
import {useCallback, useEffect, useRef, useState} from "react";
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
  const prevPath = useRef<string | null>(null);

  // 渲染期同步校正（React adjusting-state-during-render 范式）：
  // path 变更的那一帧就清掉旧 data/error，不等 effect（提交后）——
  // 否则消费方会在旧数据 + 新路径参数的组合帧里做出错误决策（如跨 kind 自动选中）。
  if (prevPath.current !== path) {
    prevPath.current = path;
    if (data !== null) setData(null);
    if (error !== null) setError(null);
  }

  useEffect(() => {
    if (path === null) {
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

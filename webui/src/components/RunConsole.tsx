/** 运行控制台：EventSource 消费 SSE 事件流（事件词表与旧 webui.js 一致）。
 * 终态后回调 onFinished（前端 refetch 面板，替代旧 htmx.ajax 刷新）。 */
import {useEffect, useRef, useState} from "react";

export interface RunEventLine {
  kind: string;
  node_id: string | null;
  message: string;
}

const TERMINAL = new Set(["run_finished", "run_failed"]);

export function RunConsole({pid, runId, onFinished}: {
  pid: string;
  runId: string;
  onFinished?: () => void;
}) {
  const [lines, setLines] = useState<RunEventLine[]>([]);
  const boxRef = useRef<HTMLDivElement>(null);
  const cbRef = useRef(onFinished);
  cbRef.current = onFinished;

  useEffect(() => {
    setLines([]);
    let cancelled = false;
    const url = `/api/projects/${encodeURIComponent(pid)}/runs/${encodeURIComponent(runId)}/events`;
    const es = new EventSource(url);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as RunEventLine;
        if (cancelled) return;
        setLines((prev) => [...prev, data]);
        if (TERMINAL.has(data.kind)) {
          es.close();
          cbRef.current?.();
        }
      } catch {
        /* 忽略畸形行 */
      }
    };
    es.onerror = () => {
      /* 断连即终（服务端终态后关流）；终态回调已触发刷新 */
      es.close();
    };
    return () => {
      cancelled = true;
      es.close();
    };
  }, [pid, runId]);

  useEffect(() => {
    const box = boxRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [lines]);

  return (
    <div className="run-log" ref={boxRef}>
      {lines.map((l, i) => (
        <p key={i} className={`line line-${l.kind}`}>{l.message}</p>
      ))}
    </div>
  );
}

"""生成运行管理（webui 设计 §6）：per-project 锁 + 内存事件队列 + SSE 流。

事件经 SimpleQueue 缓冲：晚连接的 SSE 消费者仍能取到全部历史事件（队列未消费不丢），
测试因此与线程时序无关。单人演示场景，无持久化。
"""
from __future__ import annotations

import json
import queue
import threading
import uuid
from dataclasses import dataclass

_TERMINAL = ("run_finished", "run_failed")


@dataclass(frozen=True)
class RunEvent:
    kind: str
    node_id: str | None = None
    message: str = ""


class Run:
    def __init__(self, run_id: str) -> None:
        self.id = run_id
        self.error: str | None = None
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._done = threading.Event()

    def emit(self, event: RunEvent) -> None:
        self._queue.put(event)

    def finish(self) -> None:
        self._done.set()

    def stream_sse(self):
        """阻塞消费事件 → SSE 行；终态事件后结束。"""
        while True:
            try:
                ev = self._queue.get(timeout=10)
            except queue.Empty:
                if self._done.is_set():
                    return
                continue
            payload = json.dumps({"kind": ev.kind, "node_id": ev.node_id,
                                  "message": ev.message}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            if ev.kind in _TERMINAL:
                return


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._mu = threading.Lock()

    def try_start(self, project_key: str) -> Run | None:
        with self._mu:
            lock = self._locks.setdefault(project_key, threading.Lock())
            if not lock.acquire(blocking=False):
                return None
            run = Run(uuid.uuid4().hex[:12])
            self._runs[run.id] = run
            return run

    def get(self, run_id: str) -> Run | None:
        with self._mu:
            return self._runs.get(run_id)

    def finish(self, project_key: str, run: Run) -> None:
        with self._mu:
            self._locks[project_key].release()
        run.finish()

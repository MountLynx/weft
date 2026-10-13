"""生成触发、SSE 事件序列、闸门拒绝、per-project 锁——JSON API 版。"""
import json

from tests.helpers import write_card
from tests.webutil import make_client
from weft.web.runs import RunManager


def test_run_manager_lock():
    mgr = RunManager()
    run = mgr.try_start("p1")
    assert run is not None
    assert mgr.try_start("p1") is None      # 同项目串行
    assert mgr.try_start("p2") is not None  # 异项目互不影响
    mgr.finish("p1", run)
    assert mgr.try_start("p1") is not None


def test_generate_sse_event_sequence(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/parts/sec-01/generate",
                       json={"mock": True})
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    events = []
    with client.stream("GET",
                       f"/api/projects/demo/runs/{run_id}/events") as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "run_started"
    assert kinds.count("node_started") == 1 and kinds.count("node_finished") == 1
    assert "draft_written" in kinds
    assert kinds[-1] == "run_finished"
    assert (root / "demo" / "drafts" / "sec-01.md").exists()


def test_generate_gate_rejects_with_diagnostics(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "data", "oops",
               {"id": "data-01", "status": "draft"})   # 文件名≠id → 校验错误
    resp = client.post("/api/projects/demo/parts/sec-01/generate",
                       json={"mock": True})
    assert resp.status_code == 422
    body = resp.json()
    assert "校验存在错误" in body["detail"]
    assert body["diagnostics"] and all(d["is_error"] for d in body["diagnostics"])
    assert "run_id" not in body


def test_generate_second_run_409(tmp_path):
    client, root = make_client(tmp_path)
    # 直接占住锁：绕过真实生成线程，构造并发场景
    mgr = client.app.state.runs
    run = mgr.try_start("demo")
    assert run is not None
    try:
        resp = client.post("/api/projects/demo/parts/sec-01/generate",
                           json={"mock": True})
        assert resp.status_code == 409
        assert "已有生成任务在运行" in resp.json()["detail"]
    finally:
        mgr.finish("demo", run)

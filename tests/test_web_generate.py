"""生成触发、SSE 事件序列、闸门拒绝、per-project 锁。"""
import json
import re

import pytest

pytest.importorskip("fastapi")

from tests.helpers import make_minimal_project, write_card
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
    resp = client.post("/p/demo/parts/sec-01/generate", data={"mock": "1"})
    assert resp.status_code == 200
    match = re.search(r'data-run-id="([0-9a-f]+)"', resp.text)
    assert match, resp.text
    events = []
    with client.stream("GET", f"/p/demo/runs/{match.group(1)}/events") as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "run_started"
    assert kinds.count("node_started") == 1 and kinds.count("node_finished") == 1
    assert "draft_written" in kinds
    assert kinds[-1] == "run_finished"
    assert (root / "demo" / "drafts" / "sec-01.md").exists()


def test_generate_gate_rejects_with_errors(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "data", "oops",
               {"id": "data-01", "status": "draft"})   # 文件名≠id → 校验错误
    resp = client.post("/p/demo/parts/sec-01/generate", data={"mock": "1"})
    assert resp.status_code == 200
    assert "校验存在错误" in resp.text
    assert 'data-run-id' not in resp.text

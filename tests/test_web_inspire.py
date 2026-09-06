"""灵感页：表单触发（mock）、SSE 完成、提案应用路由。"""
import json
import re

import pytest

pytest.importorskip("fastapi")

import frontmatter as fm

from tests.webutil import make_client


def test_inspire_page_renders(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/inspire")
    assert resp.status_code == 200 and "灵感" in resp.text


def test_inspire_run_finishes_with_mock(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/inspire/run", data={
        "text": "搅拌 speed up dissolving，也许温度才是主因？", "mock": "1"})
    match = re.search(r'data-run-id="([0-9a-f]+)"', resp.text)
    assert match, resp.text
    events = []
    with client.stream("GET", f"/p/demo/runs/{match.group(1)}/events") as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    assert events[-1]["kind"] == "run_finished"
    assert (root / "demo" / "inspirations").is_dir()   # 收件箱 + 报告已落盘


def test_apply_proposal_route(tmp_path):
    client, root = make_client(tmp_path)
    proposals = root / "demo" / "inspirations" / "proposals"
    proposals.mkdir(parents=True)
    proposals.joinpath("claim-01.md").write_text(fm.dumps(fm.Post("", **{
        "id": "claim-01", "claim_type": "uncited",
        "statement": "网页应用的提案。", "status": "draft"})), encoding="utf-8")
    resp = client.post("/p/demo/inspire/proposals/claim-01/apply",
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "网页应用的提案" in (root / "demo" / "metadata" / "claims" / "uncited"
                                / "claim-01.md").read_text(encoding="utf-8")
    assert not proposals.joinpath("claim-01.md").exists()

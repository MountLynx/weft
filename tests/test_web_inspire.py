"""灵感页：表单触发（mock）、SSE 完成、提案应用路由、提案对比页。"""
import json
import re

import pytest

pytest.importorskip("fastapi")

import frontmatter as fm

from tests.webutil import make_client


def _write_proposal(root, card_id: str, **meta):
    proposals = root / "demo" / "inspirations" / "proposals"
    proposals.mkdir(parents=True, exist_ok=True)
    path = proposals / f"{card_id}.md"
    path.write_text(fm.dumps(fm.Post("", **meta)), encoding="utf-8")
    return path


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


def test_proposal_compare_page(tmp_path):
    client, root = make_client(tmp_path)
    _write_proposal(root, "fact-01", id="fact-01", data=["data-01"],
                    statement="温度显著提高反应速率。", supports=["claim-01"],
                    status="draft", comment="取代 fact-01（灵感补充）")
    resp = client.get("/p/demo/inspire/proposals/fact-01")
    assert resp.status_code == 200
    assert "温度显著提高反应速率。" in resp.text      # 提案侧
    assert "温度提高速率。" in resp.text              # 当前卡侧
    assert "diff-add" in resp.text and "diff-del" in resp.text
    assert 'class="changed"' in resp.text             # statement/comment 差异高亮
    assert "data-01" in resp.text                     # 列表字段进对照表
    assert "/p/demo/inspire/proposals/fact-01/apply" in resp.text


def test_proposal_compare_page_missing_proposal(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/inspire/proposals/fact-01")
    assert resp.status_code == 404


def test_proposal_compare_page_missing_target(tmp_path):
    client, root = make_client(tmp_path)
    _write_proposal(root, "claim-99", id="claim-99", claim_type="uncited",
                    statement="无主提案。", status="draft")
    resp = client.get("/p/demo/inspire/proposals/claim-99")
    assert resp.status_code == 200
    assert "不存在" in resp.text
    assert "/apply" not in resp.text                  # 目标缺失不渲染应用按钮


def test_proposal_compare_page_unparseable(tmp_path):
    client, root = make_client(tmp_path)
    _write_proposal(root, "claim-01", id="claim-01", claim_type="weird",
                    statement="坏提案。", status="draft")
    resp = client.get("/p/demo/inspire/proposals/claim-01")
    assert resp.status_code == 200
    assert "解析失败" in resp.text
    assert "diff-del" in resp.text                    # 当前卡 vs 提案原文 raw diff
    assert "/apply" not in resp.text


def test_proposal_compare_page_id_mismatch(tmp_path):
    client, root = make_client(tmp_path)
    _write_proposal(root, "claim-01", id="claim-02", claim_type="uncited",
                    statement="错位提案。", status="draft")
    resp = client.get("/p/demo/inspire/proposals/claim-01")
    assert resp.status_code == 200
    assert "不一致" in resp.text
    assert "/apply" not in resp.text


def test_proposal_compare_page_clean_diff_hidden(tmp_path):
    client, root = make_client(tmp_path)
    src = (root / "demo" / "metadata" / "claims" / "uncited"
           / "claim-01.md")
    proposals = root / "demo" / "inspirations" / "proposals"
    proposals.mkdir(parents=True)
    proposals.joinpath("claim-01.md").write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8")
    resp = client.get("/p/demo/inspire/proposals/claim-01")
    assert resp.status_code == 200
    assert "diff-add" not in resp.text                # 无逐行差异段
    assert 'class="changed"' not in resp.text         # 无字段差异高亮
    assert "/p/demo/inspire/proposals/claim-01/apply" in resp.text


def test_inspire_page_links_compare(tmp_path):
    client, root = make_client(tmp_path)
    _write_proposal(root, "claim-01", id="claim-01", claim_type="uncited",
                    statement="提案。", status="draft")
    resp = client.get("/p/demo/inspire")
    assert 'href="/p/demo/inspire/proposals/claim-01"' in resp.text

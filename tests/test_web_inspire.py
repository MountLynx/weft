"""灵感管线：触发（mock）、SSE 完成、提案应用、提案对比 payload。"""
import json

import frontmatter as fm

from tests.webutil import make_client


def _write_proposal(root, card_id: str, **meta):
    proposals = root / "demo" / "inspirations" / "proposals"
    proposals.mkdir(parents=True, exist_ok=True)
    path = proposals / f"{card_id}.md"
    path.write_text(fm.dumps(fm.Post("", **meta)), encoding="utf-8")
    return path


def test_inspire_list_proposals(tmp_path):
    client, root = make_client(tmp_path)
    _write_proposal(root, "claim-01", id="claim-01", claim_type="uncited",
                    statement="提案。", status="draft")
    payload = client.get("/api/projects/demo/inspire").json()
    assert [p["id"] for p in payload["proposals"]] == ["claim-01"]


def test_inspire_run_finishes_with_mock(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/inspire/run", json={
        "text": "搅拌 speed up dissolving，也许温度才是主因？", "mock": True})
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    events = []
    with client.stream("GET",
                       f"/api/projects/demo/runs/{run_id}/events") as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    assert events[-1]["kind"] == "run_finished"
    assert (root / "demo" / "inspirations").is_dir()   # 收件箱 + 报告已落盘


def test_inspire_run_empty_text_422(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/api/projects/demo/inspire/run",
                       json={"text": "   ", "mock": True})
    assert resp.status_code == 422
    assert "灵感文本为空" in resp.json()["detail"]


def test_apply_proposal(tmp_path):
    client, root = make_client(tmp_path)
    proposals = root / "demo" / "inspirations" / "proposals"
    proposals.mkdir(parents=True)
    proposals.joinpath("claim-01.md").write_text(fm.dumps(fm.Post("", **{
        "id": "claim-01", "claim_type": "uncited",
        "statement": "网页应用的提案。", "status": "draft"})), encoding="utf-8")
    resp = client.post("/api/projects/demo/inspire/proposals/claim-01/apply")
    assert resp.status_code == 200 and resp.json()["ok"] is True
    assert "网页应用的提案" in (root / "demo" / "metadata" / "claims" / "uncited"
                                / "claim-01.md").read_text(encoding="utf-8")
    assert not proposals.joinpath("claim-01.md").exists()


def test_proposal_compare_payload(tmp_path):
    client, root = make_client(tmp_path)
    _write_proposal(root, "fact-01", id="fact-01", data=["data-01"],
                    statement="温度显著提高反应速率。", supports=["claim-01"],
                    status="draft", comment="取代 fact-01（灵感补充）")
    payload = client.get("/api/projects/demo/inspire/proposals/fact-01").json()
    assert payload["applicable"] is True and payload["warn"] is None
    assert payload["old_rel"] == "metadata/facts/fact-01.md"
    changed = {r["key"] for r in payload["rows"] if r["changed"]}
    assert "statement" in changed and "comment" in changed
    assert any(r["new"] == "温度显著提高反应速率。" for r in payload["rows"])
    assert any(r["old"] == "温度提高速率。" for r in payload["rows"])
    assert any(r["cls"] == "add" for r in payload["diff_rows"])


def test_proposal_compare_missing_proposal_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get(
        "/api/projects/demo/inspire/proposals/fact-01").status_code == 404


def test_proposal_compare_missing_target(tmp_path):
    client, root = make_client(tmp_path)
    _write_proposal(root, "claim-99", id="claim-99", claim_type="uncited",
                    statement="无主提案。", status="draft")
    payload = client.get("/api/projects/demo/inspire/proposals/claim-99").json()
    assert payload["applicable"] is False          # 目标缺失 fail-closed 隐藏应用
    assert "不存在" in payload["warn"]
    assert payload["raw_new"] and payload["rows"] is None


def test_proposal_compare_unparseable(tmp_path):
    client, root = make_client(tmp_path)
    _write_proposal(root, "claim-01", id="claim-01", claim_type="weird",
                    statement="坏提案。", status="draft")
    payload = client.get("/api/projects/demo/inspire/proposals/claim-01").json()
    assert payload["applicable"] is False
    assert "解析失败" in payload["warn"]
    assert payload["diff_rows"]                    # 当前卡 vs 提案原文 raw diff
    assert payload["raw_new"]                      # 解析失败回显原文兜底（旧语义）


def test_proposal_compare_id_mismatch(tmp_path):
    client, root = make_client(tmp_path)
    _write_proposal(root, "claim-01", id="claim-02", claim_type="uncited",
                    statement="错位提案。", status="draft")
    payload = client.get("/api/projects/demo/inspire/proposals/claim-01").json()
    assert payload["applicable"] is False
    assert "不一致" in payload["warn"]


def test_proposal_compare_clean_diff_hidden(tmp_path):
    client, root = make_client(tmp_path)
    src = (root / "demo" / "metadata" / "claims" / "uncited" / "claim-01.md")
    proposals = root / "demo" / "inspirations" / "proposals"
    proposals.mkdir(parents=True)
    proposals.joinpath("claim-01.md").write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8")
    payload = client.get("/api/projects/demo/inspire/proposals/claim-01").json()
    assert payload["applicable"] is True
    assert payload["diff_rows"] is None            # 无逐行差异段
    assert all(not r["changed"] for r in payload["rows"])   # 无字段差异

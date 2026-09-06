"""卡片编辑表单：渲染、写回、校验错误回显、claim_type 迁移。"""
import pytest

pytest.importorskip("fastapi")

from weft.store.loader import load_project
from tests.webutil import make_client


def test_edit_form_renders_fields(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/cards/fact/fact-01/edit")
    assert resp.status_code == 200
    assert "statement" in resp.text and "data-01" in resp.text  # data 多选已勾选


def test_edit_save_round_trip(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/edit", data={
        "data": ["data-01"], "statement": "改后的陈述。", "supports": ["claim-01"],
        "status": "approved", "comment": "ok"}, follow_redirects=False)
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.facts["fact-01"].statement == "改后的陈述。"


def test_edit_validation_error_rerenders(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/edit", data={
        "data": [], "statement": "", "supports": [],   # data 空违反 min_length=1
        "status": "approved", "comment": ""})
    assert resp.status_code == 200
    assert "data" in resp.text and "1" in resp.text   # 错误回显
    project, _ = load_project(root / "demo")
    assert project.facts["fact-01"].statement == "温度提高速率。"   # 未落盘


def test_claim_type_edit_moves_file(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/claim/claim-01/edit", data={
        "claim_type": "cited", "cites": ["key2020"], "statement": "温度有正效应。",
        "status": "approved", "comment": ""}, follow_redirects=False)
    assert resp.status_code == 303
    assert (root / "demo" / "metadata" / "claims" / "cited" / "claim-01.md").exists()
    assert not (root / "demo" / "metadata" / "claims" / "uncited" / "claim-01.md").exists()

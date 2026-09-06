"""卡片新建：id 自动分配/预填、创建落盘、重名拒绝。"""
import pytest

pytest.importorskip("fastapi")

from weft.store.loader import load_project
from tests.webutil import make_client


def test_new_form_prefills_next_id(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/cards/fact/new")
    assert resp.status_code == 200
    assert 'value="fact-02"' in resp.text and 'readonly' in resp.text


def test_create_writes_card(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/new", data={
        "id": "fact-02", "data": ["data-01"], "statement": "新事实。",
        "supports": [], "status": "draft", "comment": ""}, follow_redirects=False)
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.facts["fact-02"].statement == "新事实。"


def test_create_duplicate_id_rejected(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/new", data={
        "id": "fact-01", "data": ["data-01"], "statement": "重复 id。",
        "supports": [], "status": "draft", "comment": ""})
    assert resp.status_code == 200   # 回显错误，不落盘
    assert "fact-01" in resp.text
    project, _ = load_project(root / "demo")
    assert project.facts["fact-01"].statement == "温度提高速率。"


def test_create_empty_id_rejected(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/method/new", data={
        "id": "", "statement": "空 id。", "protocol": "步骤", "derived_from": [],
        "status": "draft", "comment": ""})
    assert resp.status_code == 200
    assert "id 非法" in resp.text
    assert not (root / "demo" / "metadata" / "methods" / ".md").exists()
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)   # 项目仍然可用


def test_create_traversal_id_rejected(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/method/new", data={
        "id": "../evil", "statement": "逃逸。", "protocol": "步骤",
        "derived_from": [], "status": "draft", "comment": ""})
    assert resp.status_code == 200
    assert "id 非法" in resp.text
    assert not (root / "demo" / "metadata" / "evil.md").exists()
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)

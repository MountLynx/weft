"""卡片新建：id 自动分配/预填、创建落盘、重名拒绝——JSON API 版。"""
from weft.store.loader import load_project
from tests.helpers import write_card
from tests.webutil import make_client


def test_form_spec_prefills_next_id(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo/card-forms/fact").json()
    assert payload["is_new"] is True and payload["id_widget"] == "auto"
    assert payload["prefilled_id"] == "fact-02"
    assert {s["name"] for s in payload["specs"]} >= {"data", "statement", "supports"}


def test_create_custom_semantic_id(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/fact", json={
        "id": "rate-jumps-above-60c", "data": ["data-01"],
        "statement": "语义 id 可直接落盘。", "supports": [],
        "status": "draft", "comment": ""})
    assert resp.status_code == 200 and resp.json()["id"] == "rate-jumps-above-60c"
    assert (root / "demo" / "metadata" / "facts" / "rate-jumps-above-60c.md").exists()


def test_create_writes_card(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/fact", json={
        "id": "fact-02", "data": ["data-01"], "statement": "新事实。",
        "supports": [], "status": "draft", "comment": ""})
    assert resp.status_code == 200
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.facts["fact-02"].statement == "新事实。"


def test_create_duplicate_id_rejected(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/fact", json={
        "id": "fact-01", "data": ["data-01"], "statement": "重复 id。",
        "supports": [], "status": "draft", "comment": ""})
    assert resp.status_code == 422                 # 错误回传，不落盘
    assert "fact-01" in resp.json()["errors"]["id"]
    project, _ = load_project(root / "demo")
    assert project.facts["fact-01"].statement == "温度提高速率。"


def test_create_empty_id_rejected(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/method", json={
        "id": "", "statement": "空 id。", "protocol": "步骤", "derived_from": [],
        "status": "draft", "comment": ""})
    assert resp.status_code == 422 and "id 非法" in resp.json()["errors"]["id"]
    assert not (root / "demo" / "metadata" / "methods" / ".md").exists()
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)   # 项目仍然可用


def test_create_traversal_id_rejected(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/method", json={
        "id": "../evil", "statement": "逃逸。", "protocol": "步骤",
        "derived_from": [], "status": "draft", "comment": ""})
    assert resp.status_code == 422 and "id 非法" in resp.json()["errors"]["id"]
    assert not (root / "demo" / "metadata" / "evil.md").exists()
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)


def test_multiselect_choices_carry_digest(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "data", "data-02",
               {"id": "data-02", "refs": [], "description": "备用测量数据",
                "status": "approved"})
    payload = client.get("/api/projects/demo/card-forms/fact").json()
    assert "data-02" in payload["choices"]["data_ids"]
    # labels 为裸摘要（前端组合 "id · 摘要" 展示，提交值仍是裸 id）
    assert payload["labels"]["data_ids"]["data-02"] == "备用测量数据"


def test_param_method_select_shows_digest(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "methods", "qpcr",
               {"id": "qpcr", "statement": "qPCR 三步法。", "protocol": "p",
                "status": "approved"})
    payload = client.get("/api/projects/demo/card-forms/param").json()
    assert "qPCR 三步法。" in payload["labels"]["method_ids"]["qpcr"]
    assert payload["id_widget"] == "slug"          # param 手输 slug

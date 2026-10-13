"""卡片编辑：回显、写回、校验错误回显、claim_type 迁移——JSON API 版。"""
from weft.store.loader import load_project
from tests.webutil import make_client


def test_edit_payload_carries_values(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo/cards/fact/fact-01/edit").json()
    assert payload["values"]["data"] == ["data-01"]      # data 多选已回显
    assert "温度提高速率" in payload["values"]["statement"]


def test_edit_save_round_trip(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.patch("/api/projects/demo/cards/fact/fact-01", json={
        "data": ["data-01"], "statement": "改后的陈述。", "supports": ["claim-01"],
        "status": "approved", "comment": "ok"})
    assert resp.status_code == 200
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.facts["fact-01"].statement == "改后的陈述。"


def test_edit_validation_error_422_not_written(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.patch("/api/projects/demo/cards/fact/fact-01", json={
        "data": [], "statement": "", "supports": [],   # data 空违反 min_length=1
        "status": "approved", "comment": ""})
    assert resp.status_code == 422 and resp.json()["errors"]   # 字段级错误回显
    project, _ = load_project(root / "demo")
    assert project.facts["fact-01"].statement == "温度提高速率。"   # 未落盘


def test_edit_optional_none_field_round_trip(tmp_path):
    client, root = make_client(tmp_path)
    payload = client.get("/api/projects/demo/cards/data/data-01/edit").json()
    assert payload["values"]["source"] == ""        # None 归一为空串（防字面 "None" 写回）
    resp = client.patch("/api/projects/demo/cards/data/data-01", json={
        "refs": ["fig-01a"], "source": "", "description": "",
        "status": "approved", "comment": ""})
    assert resp.status_code == 200
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.data_cards["data-01"].source in (None, "")   # 空串不损坏为字面 "None"


def test_claim_type_edit_moves_file(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.patch("/api/projects/demo/cards/claim/claim-01", json={
        "claim_type": "cited", "cites": ["key2020"], "statement": "温度有正效应。",
        "status": "approved", "comment": ""})
    assert resp.status_code == 200
    assert (root / "demo" / "metadata" / "claims" / "cited" / "claim-01.md").exists()
    assert not (root / "demo" / "metadata" / "claims" / "uncited" / "claim-01.md").exists()


def test_rename_card(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/fact/fact-01/rename",
                       json={"new_id": "temp-rate"})
    assert resp.status_code == 200 and resp.json()["id"] == "temp-rate"
    assert (root / "demo" / "metadata" / "facts" / "temp-rate.md").exists()
    assert not (root / "demo" / "metadata" / "facts" / "fact-01.md").exists()


def test_rename_collision_422(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/fact/fact-01/rename",
                       json={"new_id": "claim-01"})
    assert resp.status_code == 422 and "E-NEW-COLLISION" in resp.json()["detail"]
    assert (root / "demo" / "metadata" / "facts" / "fact-01.md").exists()

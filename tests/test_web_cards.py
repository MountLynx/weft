"""卡片列表、详情与审阅（status/comment 写回）——JSON API 版。"""
from weft.store.loader import load_project
from tests.helpers import make_managed_project, write_card
from tests.webutil import make_client


def test_cards_overview_and_list(tmp_path):
    client, _ = make_client(tmp_path)
    counts = client.get("/api/projects/demo/cards").json()["counts"]
    assert counts["fact"] == 1 and counts["note"] == 1
    payload = client.get("/api/projects/demo/cards/fact").json()
    assert payload["label"] == "fact 卡"
    assert [r["id"] for r in payload["rows"]] == ["fact-01"]
    assert payload["rows"][0]["key"] == "温度提高速率。"   # key = KEY_FIELD 摘要


def test_card_detail_payload(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo/cards/fact/fact-01").json()
    assert payload["id"] == "fact-01" and payload["status"] == "approved"
    assert "温度提高速率" in payload["fields"]["statement"]
    assert payload["rel"] == "metadata/facts/fact-01.md"
    assert payload["fixable"] is False


def test_unknown_kind_and_card_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/api/projects/demo/cards/bogus").status_code == 404
    assert client.get("/api/projects/demo/cards/fact/fact-99").status_code == 404


def test_review_updates_file(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/fact/fact-01/status",
                       json={"status": "rejected", "comment": "表述有误"})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.facts["fact-01"].status == "rejected"
    assert project.facts["fact-01"].comment == "表述有误"


def test_review_invalid_status_400(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/fact/fact-01/status",
                       json={"status": "bogus", "comment": ""})
    assert resp.status_code == 400
    project, _ = load_project(root / "demo")
    assert project.facts["fact-01"].status == "approved"


def test_review_surface_survives_validation_errors(tmp_path):
    # unmanaged 提案 draft note（id 不在 bib）触发 E-NOTE-NOT-IN-BIB → 项目校验错误：
    # 卡列表/审阅 POST 不得 404（死锁修复：UI 造出的状态必须能经 UI 修复）。
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "notes", "li2021",
               {"id": "li2021", "summary": "", "status": "draft"})
    assert client.get("/api/projects/demo/cards").status_code == 200
    assert client.get("/api/projects/demo/cards/note").status_code == 200
    resp = client.post("/api/projects/demo/cards/note/li2021/status",
                       json={"status": "approved", "comment": ""})
    assert resp.status_code == 200
    project, _ = load_project(root / "demo")
    assert project.notes["li2021"].status == "approved"


def test_rename_to_bib_key_clears_validation_error(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "notes", "li2021",
               {"id": "li2021", "summary": "s", "status": "draft"})
    bib = root / "demo" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8")
                   + "@article{altkey2021,\n  title = {T},\n  year = {2021},\n}\n",
                   encoding="utf-8")
    resp = client.post("/api/projects/demo/cards/note/li2021/rename",
                       json={"new_id": "altkey2021"})
    assert resp.status_code == 200 and resp.json()["id"] == "altkey2021"
    payload = client.get("/api/projects/demo").json()
    assert payload["available"] is True            # 改名后校验错误消除


ENTRY_YAML = "type: article\ntitle: T\nauthor:\n- A, B\nyear: 2020\njournal: J\nvolume: '1'\n"


def _managed_web_client(tmp_path):
    client, root = make_client(tmp_path)
    make_managed_project(root / "demo")
    return client, root


def test_note_edit_payload_shows_entry_yaml(tmp_path):
    client, _ = _managed_web_client(tmp_path)
    payload = client.get("/api/projects/demo/cards/note/key2020/edit").json()
    assert payload["is_new"] is False
    assert "type: article" in payload["values"]["entry"]   # 既有 entry 以 YAML 文本回显


def test_note_edit_saves_entry(tmp_path):
    client, root = _managed_web_client(tmp_path)
    resp = client.patch("/api/projects/demo/cards/note/key2020", json={
        "summary": "s", "pdf": "", "entry": ENTRY_YAML,
        "status": "approved", "comment": ""})
    assert resp.status_code == 200
    project, _ = load_project(root / "demo")
    assert project.notes["key2020"].entry.title == "T"


def test_approve_note_managed_syncs_bib(tmp_path):
    client, root = _managed_web_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/note/key2020/status",
                       json={"status": "approved", "comment": ""})
    body = resp.json()
    assert resp.status_code == 200 and body["bib"] == "bib_updated"
    content = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert content.startswith("%") and "@article{key2020" in content


def test_approve_note_unmanaged_no_bib_flag(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/note/key2020/status",
                       json={"status": "approved", "comment": ""})
    assert resp.status_code == 200 and resp.json()["bib"] is None


def test_approve_note_managed_bib_error_rejected_422(tmp_path):
    """E-BIB-VALUE 前置为落盘前拒绝：坏值批准被 422 挡下，盘上零毒化。"""
    client, root = _managed_web_client(tmp_path)
    before = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    write_card(root / "demo" / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "draft",
                "entry": {"type": "article", "title": "{T", "year": 2020}})
    resp = client.post("/api/projects/demo/cards/note/key2020/status",
                       json={"status": "approved", "comment": ""})
    assert resp.status_code == 422 and "E-BIB-VALUE" in resp.json()["detail"]
    project, _ = load_project(root / "demo")
    assert project.notes["key2020"].status == "draft"     # 未落盘
    assert (root / "demo" / "references.bib").read_text(encoding="utf-8") == before


def test_edit_entry_value_error_field_error(tmp_path):
    client, root = _managed_web_client(tmp_path)
    before = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    resp = client.patch("/api/projects/demo/cards/note/key2020", json={
        "summary": "s", "pdf": "",
        "entry": "title: 'Smith {O''Brien'\nyear: 2020\ntype: article\n",
        "status": "approved", "comment": ""})
    assert resp.status_code == 422
    assert "E-BIB-VALUE" in resp.json()["errors"]["entry"]
    card_path = root / "demo" / "metadata" / "notes" / "key2020.md"
    assert "O'Brien" not in card_path.read_text(encoding="utf-8")      # 未落盘
    assert (root / "demo" / "references.bib").read_text(encoding="utf-8") == before


def test_review_bad_entry_blocked_422(tmp_path):
    client, root = _managed_web_client(tmp_path)
    write_card(root / "demo" / "metadata" / "notes", "bad2020",
               {"id": "bad2020", "summary": "s", "status": "draft",
                "entry": {"type": "article", "title": "{T", "year": 2020}})
    resp = client.post("/api/projects/demo/cards/note/bad2020/status",
                       json={"status": "approved", "comment": ""})
    assert resp.status_code == 422 and "E-BIB-VALUE" in resp.json()["detail"]
    project, _ = load_project(root / "demo")
    assert project.notes["bad2020"].status == "draft"                 # 批准被阻止


def test_new_note_approved_syncs_bib(tmp_path):
    client, root = _managed_web_client(tmp_path)
    # 夹具自带 note key2020（approved+entry）；重名会 422，
    # 故删掉预置卡以走「新建即批准」路径（断言与原意不变）
    (root / "demo" / "metadata" / "notes" / "key2020.md").unlink()
    resp = client.post("/api/projects/demo/cards/note", json={
        "id": "key2020", "summary": "s", "pdf": "",
        "entry": "type: article\ntitle: T\nyear: 2020\n",
        "status": "approved", "comment": ""})
    assert resp.status_code == 200 and resp.json()["bib"] == "bib_updated"
    content = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert "@article{key2020" in content and "title = {T}" in content


def test_new_note_draft_no_bib_flag(tmp_path):
    client, root = _managed_web_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/note", json={
        "id": "new2021", "summary": "s", "pdf": "",
        "entry": "type: article\ntitle: N\nyear: 2021\n",
        "status": "draft", "comment": ""})
    assert resp.status_code == 200 and resp.json()["bib"] is None


def test_reject_note_removes_from_bib(tmp_path):
    client, root = _managed_web_client(tmp_path)
    resp = client.post("/api/projects/demo/cards/note/key2020/status",
                       json={"status": "rejected", "comment": ""})
    assert resp.json()["bib"] == "bib_updated"
    content = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert "@article{key2020" not in content


def test_detail_payload_marks_fixable(tmp_path):
    client, root = make_client(tmp_path)
    # fixable 前置：非 rejected + entry 非空 + id 不在 bib（bibgen.fixable_notes §3.5）
    write_card(root / "demo" / "metadata" / "notes", "li2021",
               {"id": "li2021", "summary": "s", "status": "draft",
                "entry": {"type": "article", "title": "T", "year": 2021}})
    assert client.get(
        "/api/projects/demo/cards/note/li2021").json()["fixable"] is True
    assert client.get(
        "/api/projects/demo/cards/note/key2020").json()["fixable"] is False


def test_unmanaged_entry_error_not_prechecked(tmp_path):
    """unmanaged 项目 entry 坏值无消费方：预检不设门会挡住无关编辑（T7 复审 Minor）。"""
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "旧", "status": "approved",
                "entry": {"type": "article", "title": "{T", "year": 2020}})
    resp = client.patch("/api/projects/demo/cards/note/key2020", json={
        "summary": "新概括", "pdf": "",
        "entry": "title: 'Smith {O''Brien'\nyear: 2020\ntype: article\n",
        "status": "approved", "comment": ""})
    assert resp.status_code == 200
    project, _ = load_project(root / "demo")
    assert project.notes["key2020"].summary == "新概括"    # 无关编辑照常落盘

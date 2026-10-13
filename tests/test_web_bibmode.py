"""bib 模式切换与一键修复 API（bib-mode-fix 设计 §4）。"""
from weft.store.loader import load_project
from tests.helpers import NOTE_ENTRY, make_managed_project, write_card
from tests.webutil import make_client


def _poison(root):
    """unmanaged + draft note（带 entry，不在 bib）→ E-NOTE-NOT-IN-BIB 报错项目。"""
    write_card(root / "demo" / "metadata" / "notes", "li2021",
               {"id": "li2021", "summary": "s", "status": "draft",
                "entry": dict(NOTE_ENTRY)})


def test_switch_confirm_payload(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo/bib/switch",
                         params={"to": "managed"}).json()
    assert payload["to"] == "managed" and payload["error"] is None
    assert "key2020" in payload["plan"]["hand_only_entries"]   # 预检警告逐条列出
    assert "notes_not_in_bib" in payload["plan"]


def test_switch_confirm_unknown_target_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/api/projects/demo/bib/switch",
                      params={"to": "bogus"}).status_code == 404


def test_switch_post_flips_mode(tmp_path):
    client, root = make_client(tmp_path)
    make_managed_project(root / "demo")
    resp = client.post("/api/projects/demo/bib/switch", json={"to": "unmanaged"})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    project, _ = load_project(root / "demo")
    assert project.bib_managed is False


def test_switch_post_precondition_failure_422(tmp_path):
    client, root = make_client(tmp_path)
    (root / "demo" / "_quarto.yml").write_text(
        'project:\n  type: default\n', encoding="utf-8")   # 未声明 bibliography
    resp = client.post("/api/projects/demo/bib/switch", json={"to": "managed"})
    assert resp.status_code == 422 and "E-BIB-MODE" in resp.json()["detail"]


def test_dashboard_shows_bib_block(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo").json()
    assert payload["bib_managed"] is False
    assert payload["bib_files"] == ["references.bib"]


def test_fix_post_added_clears_error(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    resp = client.post("/api/projects/demo/bib/fix/li2021")
    assert resp.status_code == 200 and resp.json()["result"] == "added"
    text = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert "@article{li2021," in text
    assert client.get("/api/projects/demo").json()["available"] is True


def test_fix_post_present(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    bib = root / "demo" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8")
                   + "@article{li2021,\n  title = {T},\n  year = {2021},\n}\n",
                   encoding="utf-8")
    resp = client.post("/api/projects/demo/bib/fix/li2021")
    assert resp.json()["result"] == "present"


def test_fix_post_error_branch(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    (root / "demo" / "_quarto.yml").write_text(
        'project:\n  type: default\n', encoding="utf-8")   # 未声明 bibliography
    resp = client.post("/api/projects/demo/bib/fix/li2021")
    assert resp.status_code == 200 and resp.json()["result"] == "error"


def test_fixable_visibility_in_detail_and_diagnostics(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    assert client.get(
        "/api/projects/demo/cards/note/li2021").json()["fixable"] is True
    assert client.get(
        "/api/projects/demo/cards/note/key2020").json()["fixable"] is False
    payload = client.get("/api/projects/demo/diagnostics").json()
    assert payload["fixable"] == {"metadata/notes/li2021.md": "li2021"}

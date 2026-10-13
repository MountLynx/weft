"""bib 模式切换与一键修复路由（bib-mode-fix 设计 §4）。"""
import pytest

pytest.importorskip("fastapi")

from weft.store.loader import load_project
from tests.helpers import (NOTE_ENTRY, make_managed_project, write_card)
from tests.webutil import make_client


def _poison(root):
    """unmanaged + draft note（带 entry，不在 bib）→ E-NOTE-NOT-IN-BIB 报错项目。"""
    write_card(root / "demo" / "metadata" / "notes", "li2021",
               {"id": "li2021", "summary": "s", "status": "draft",
                "entry": dict(NOTE_ENTRY)})


def test_switch_confirm_renders_report(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/bib/switch?to=managed")
    assert resp.status_code == 200
    assert "key2020" in resp.text            # hand_only_entries 警告逐条列出
    assert "确认切换" in resp.text


def test_switch_confirm_unknown_target_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/demo/bib/switch?to=bogus").status_code == 404


def test_switch_post_flips_mode(tmp_path):
    client, root = make_client(tmp_path)
    make_managed_project(root / "demo")
    resp = client.post("/p/demo/bib/switch", data={"to": "unmanaged"},
                       follow_redirects=False)
    assert resp.status_code == 303
    project, _ = load_project(root / "demo")
    assert project.bib_managed is False
    assert client.get("/p/demo/?bibmode=switched").status_code == 200


def test_switch_post_precondition_failure_rerenders(tmp_path):
    client, root = make_client(tmp_path)
    (root / "demo" / "_quarto.yml").write_text(
        'project:\n  type: default\n', encoding="utf-8")   # 未声明 bibliography
    resp = client.post("/p/demo/bib/switch", data={"to": "managed"})
    assert resp.status_code == 200
    assert "E-BIB-MODE" in resp.text


def test_dashboard_shows_bib_block(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/")
    assert "bib 模式" in resp.text and "unmanaged" in resp.text
    assert "/p/demo/bib/switch?to=managed" in resp.text


def test_fix_post_added_clears_error(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    resp = client.post("/p/demo/bib/fix/li2021", data={"back": "card"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "/cards/note/li2021?fix=added" in resp.headers["location"]
    text = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert "@article{li2021," in text
    assert 'badge rejected">不可用' not in client.get("/p/demo/").text


def test_fix_post_present(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    bib = root / "demo" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8")
                   + "@article{li2021,\n  title = {T},\n  year = {2021},\n}\n",
                   encoding="utf-8")
    resp = client.post("/p/demo/bib/fix/li2021", data={"back": "diagnostics"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "diagnostics?fix=present" in resp.headers["location"]


def test_fix_post_error_branch(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    (root / "demo" / "_quarto.yml").write_text(
        'project:\n  type: default\n', encoding="utf-8")   # 未声明 bibliography
    resp = client.post("/p/demo/bib/fix/li2021", data={"back": "diagnostics"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "diagnostics?fix=error" in resp.headers["location"]


def test_note_detail_fix_button_visibility(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    assert "一键修复" in client.get("/p/demo/cards/note/li2021").text
    assert "一键修复" not in client.get("/p/demo/cards/note/key2020").text
    diag = client.get("/p/demo/diagnostics").text
    assert "bib/fix/li2021" in diag

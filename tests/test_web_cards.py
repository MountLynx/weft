"""卡片列表、详情与审阅（status/comment 写回）。"""
import pytest

pytest.importorskip("fastapi")

from weft.store.loader import load_project
from tests.helpers import make_managed_project, write_card
from tests.webutil import make_client


def test_cards_overview_and_list(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/demo/cards").status_code == 200
    resp = client.get("/p/demo/cards/fact")
    assert resp.status_code == 200 and "fact-01" in resp.text


def test_card_detail_renders(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/cards/fact/fact-01")
    assert resp.status_code == 200
    assert "fact-01" in resp.text and "温度提高速率" in resp.text


def test_unknown_kind_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/demo/cards/bogus").status_code == 404
    assert client.get("/p/demo/cards/fact/fact-99").status_code == 404


def test_review_updates_file(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/status",
                       data={"status": "rejected", "comment": "表述有误"},
                       follow_redirects=False)
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.facts["fact-01"].status == "rejected"
    assert project.facts["fact-01"].comment == "表述有误"


def test_review_invalid_status_400(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/status",
                       data={"status": "bogus", "comment": ""})
    assert resp.status_code == 400
    project, _ = load_project(root / "demo")
    assert project.facts["fact-01"].status == "approved"


ENTRY_YAML = "type: article\ntitle: T\nauthor:\n- A, B\nyear: 2020\njournal: J\nvolume: '1'\n"


def _managed_web_client(tmp_path):
    client, root = make_client(tmp_path)
    make_managed_project(root / "demo")
    return client, root


def test_note_edit_form_shows_entry_yaml(tmp_path):
    client, _ = _managed_web_client(tmp_path)
    resp = client.get("/p/demo/cards/note/key2020/edit")
    assert resp.status_code == 200 and 'name="entry"' in resp.text
    assert "type: article" in resp.text          # 既有 entry 以 YAML 文本回显


def test_note_edit_saves_entry(tmp_path):
    client, root = _managed_web_client(tmp_path)
    resp = client.post("/p/demo/cards/note/key2020/edit", data={
        "summary": "s", "pdf": "", "entry": ENTRY_YAML,
        "status": "approved", "comment": ""}, follow_redirects=False)
    assert resp.status_code == 303
    project, _ = load_project(root / "demo")
    assert project.notes["key2020"].entry.title == "T"


def test_approve_note_managed_syncs_bib(tmp_path):
    client, root = _managed_web_client(tmp_path)
    resp = client.post("/p/demo/cards/note/key2020/status",
                       data={"status": "approved", "comment": ""},
                       follow_redirects=False)
    assert resp.status_code == 303 and "bib=bib_updated" in resp.headers["location"]
    content = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert content.startswith("%") and "@article{key2020" in content


def test_approve_note_unmanaged_no_bib_flag(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/note/key2020/status",
                       data={"status": "approved", "comment": ""},
                       follow_redirects=False)
    assert resp.status_code == 303 and "bib=" not in resp.headers["location"]


def test_approve_note_managed_bib_error_flag(tmp_path):
    """E-BIB-VALUE 前置为落盘前拒绝后：坏值批准被 400 挡下，盘上零毒化。

    （原「批准后 bib_error 旗标」契约已废除——旗标降级为纯防御路径，正常流不可达。）
    """
    client, root = _managed_web_client(tmp_path)
    before = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    # 花括号不平衡的 entry 若直接以 approved 落盘，validate_project 会判 E-BIB-VALUE
    # 使项目「不可用」（请求级 404），故以 draft 落盘、经批准动作触发预检拒绝
    write_card(root / "demo" / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "draft",
                "entry": {"type": "article", "title": "{T", "year": 2020}})
    resp = client.post("/p/demo/cards/note/key2020/status",
                       data={"status": "approved", "comment": ""},
                       follow_redirects=False)
    assert resp.status_code == 400 and "E-BIB-VALUE" in resp.text
    project, _ = load_project(root / "demo")
    assert project.notes["key2020"].status == "draft"     # 未落盘
    assert (root / "demo" / "references.bib").read_text(encoding="utf-8") == before


def test_edit_entry_value_error_field_error(tmp_path):
    client, root = _managed_web_client(tmp_path)
    before = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    resp = client.post("/p/demo/cards/note/key2020/edit", data={
        "summary": "s", "pdf": "", "entry": "title: 'Smith {O''Brien'\nyear: 2020\ntype: article\n",
        "status": "approved", "comment": ""})
    assert resp.status_code == 200 and "E-BIB-VALUE" in resp.text
    card_path = root / "demo" / "metadata" / "notes" / "key2020.md"
    assert "O'Brien" not in card_path.read_text(encoding="utf-8")      # 未落盘
    assert (root / "demo" / "references.bib").read_text(encoding="utf-8") == before


def test_review_bad_entry_blocked_400(tmp_path):
    client, root = _managed_web_client(tmp_path)
    write_card(root / "demo" / "metadata" / "notes", "bad2020",
               {"id": "bad2020", "summary": "s", "status": "draft",
                "entry": {"type": "article", "title": "{T", "year": 2020}})
    resp = client.post("/p/demo/cards/note/bad2020/status",
                       data={"status": "approved", "comment": ""})
    assert resp.status_code == 400 and "E-BIB-VALUE" in resp.text
    project, _ = load_project(root / "demo")
    assert project.notes["bad2020"].status == "draft"                 # 批准被阻止


def test_new_note_approved_syncs_bib(tmp_path):
    client, root = _managed_web_client(tmp_path)
    # 夹具自带 note key2020（approved+entry）；create_card 遇重名会 409 rerender，
    # 故删掉预置卡以走「新建即批准」路径（断言与原意不变）
    (root / "demo" / "metadata" / "notes" / "key2020.md").unlink()
    resp = client.post("/p/demo/cards/note/new", data={
        "id": "key2020", "summary": "s", "pdf": "",
        "entry": "type: article\ntitle: T\nyear: 2020\n",
        "status": "approved", "comment": ""}, follow_redirects=False)
    assert resp.status_code == 303 and "bib=bib_updated" in resp.headers["location"]
    content = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert "@article{key2020" in content and "title = {T}" in content


def test_new_note_draft_no_bib_flag(tmp_path):
    client, root = _managed_web_client(tmp_path)
    resp = client.post("/p/demo/cards/note/new", data={
        "id": "new2021", "summary": "s", "pdf": "",
        "entry": "type: article\ntitle: N\nyear: 2021\n",
        "status": "draft", "comment": ""}, follow_redirects=False)
    assert resp.status_code == 303 and "bib=" not in resp.headers["location"]


def test_reject_note_removes_from_bib(tmp_path):
    client, root = _managed_web_client(tmp_path)
    resp = client.post("/p/demo/cards/note/key2020/status",
                       data={"status": "rejected", "comment": ""},
                       follow_redirects=False)
    assert "bib=bib_updated" in resp.headers["location"]
    content = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert "@article{key2020" not in content


def test_detail_banner_success_renders(tmp_path):
    client, _ = _managed_web_client(tmp_path)
    resp = client.get("/p/demo/cards/note/key2020?bib=bib_updated")
    assert resp.status_code == 200 and "已同步" in resp.text


def test_unmanaged_entry_error_not_prechecked(tmp_path):
    """unmanaged 项目 entry 坏值无消费方：预检不设门会挡住无关编辑（T7 复审 Minor）。"""
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "旧", "status": "approved",
                "entry": {"type": "article", "title": "{T", "year": 2020}})
    resp = client.post("/p/demo/cards/note/key2020/edit", data={
        "summary": "新概括", "pdf": "",
        "entry": "title: 'Smith {O''Brien'\nyear: 2020\ntype: article\n",
        "status": "approved", "comment": ""}, follow_redirects=False)
    assert resp.status_code == 303
    project, _ = load_project(root / "demo")
    assert project.notes["key2020"].summary == "新概括"    # 无关编辑照常落盘

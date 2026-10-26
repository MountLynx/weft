"""章节标签 WebUI API（card-chapters 设计 §5.1）：rows / 面板素材区 / 表单规格。"""
from tests.helpers import write_card
from tests.webutil import make_client


def test_web_card_list_chapters(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "已引用断言。",
                "cites": ["key2020"], "chapters": ["introduction", "results"],
                "status": "approved"})
    rows = {r["id"]: r
            for r in client.get("/api/projects/demo/cards/claim").json()["rows"]}
    assert rows["claim-02"]["chapters"] == ["introduction", "results"]
    assert rows["claim-01"]["chapters"] == []


def test_web_part_panel_chapter_cards(tmp_path):
    """面板带 chapter / chapter_cards：章节匹配、全状态、used 标记。"""
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "已引用断言。",
                "cites": ["key2020"], "chapters": ["Results"], "status": "draft"})
    write_card(root / "demo" / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-01"], "statement": "补充事实。",
                "chapters": ["introduction"], "status": "approved"})
    payload = client.get("/api/projects/demo/parts/sec-01").json()
    assert payload["chapter"] == "01-results"
    assert payload["chapter_norm"] == "results"
    cards = {c["id"]: c for c in payload["chapter_cards"]}
    # claim-02 归一化匹配且状态保留；fact-02 章节不匹配被排除；key2020 无标签不在内
    assert set(cards) == {"claim-02"}
    assert cards["claim-02"] == {"id": "claim-02", "kind": "claim",
                                 "status": "draft", "key": "已引用断言。",
                                 "used": False}


def test_web_part_panel_chapter_used_flag(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "已引用断言。",
                "cites": ["key2020"], "chapters": ["results"], "status": "approved"})
    write_card(root / "demo" / "narrative" / "01-results", "part-01",
               {"id": "sec-01", "section": "Results",
                "nodes": [{"id": "para-01-01", "purpose": "describe",
                           "uses": [{"id": "fact-01", "role": "evidence"},
                                    {"id": "claim-02", "role": "background"}],
                           "status": "approved"}]})
    payload = client.get("/api/projects/demo/parts/sec-01").json()
    cards = {c["id"]: c for c in payload["chapter_cards"]}
    assert cards["claim-02"]["used"] is True


def test_web_form_spec_tags_widget(tmp_path):
    """六卡种表单规格带 chapters（tags 控件）；已知章节进 datalist choices；
    values 往返：列表 ⇄ 逗号文本；PATCH 解析回列表。"""
    client, root = make_client(tmp_path)
    spec = client.get("/api/projects/demo/card-forms/claim").json()
    chapters = [s for s in spec["specs"] if s["name"] == "chapters"]
    assert chapters and chapters[0]["widget"] == "tags"
    assert chapters[0]["choices"] == "chapter_names"
    assert spec["choices"]["chapter_names"] == ["results"]
    assert spec["values"]["chapters"] == ""

    write_card(root / "demo" / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "已引用断言。",
                "cites": ["key2020"], "chapters": ["introduction", "results"],
                "status": "approved"})
    edit = client.get(
        "/api/projects/demo/cards/claim/claim-02/edit").json()
    assert edit["values"]["chapters"] == "introduction, results"

    resp = client.patch("/api/projects/demo/cards/claim/claim-02",
                        json={"claim_type": "cited",
                              "statement": "已引用断言。",
                              "cites": ["key2020"],
                              "chapters": "introduction, 03-results, introduction",
                              "status": "approved", "comment": ""})
    assert resp.status_code == 200, resp.text
    from weft.store.loader import load_project
    project, _ = load_project(root / "demo")
    # 逗号分隔解析 + 去重保序
    assert project.claims["claim-02"].chapters == ["introduction", "03-results"]

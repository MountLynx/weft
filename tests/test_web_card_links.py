"""卡片链路端点 /cards/links（webui-card-links 设计 §2/§8）：实时反向索引 + 正向链接。"""
from tests.helpers import write_card
from tests.webutil import make_client


def test_card_links_payload(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "methods", "m-xt",
               {"id": "m-xt", "statement": "s", "protocol": "p",
                "derived_from": ["key2020"], "status": "approved"})
    write_card(root / "demo" / "metadata" / "methods" / "params", "p-xt",
               {"id": "p-xt", "method": "m-xt", "values": {"rate": "5"},
                "derived_from": ["key2020"], "status": "draft"})
    write_card(root / "demo" / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited",
                "statement": "已引用断言。", "cites": ["key2020"],
                "status": "draft"})
    ents = client.get("/api/projects/demo/cards/links").json()["entities"]
    assert set(ents) == {"data-01", "fact-01", "claim-01", "claim-02",
                         "key2020", "m-xt", "p-xt"}
    assert ents["fact-01"]["links"] == {"data": ["data-01"],
                                        "claim": ["claim-01"]}
    assert ents["claim-01"]["links"] == {"note": []}
    assert ents["claim-02"]["links"] == {"note": ["key2020"]}
    assert ents["data-01"]["links"] == {}
    assert ents["fact-01"]["summary"] == "温度提高速率。"
    assert ents["data-01"]["referenced_by"]["facts"] == ["fact-01"]
    assert ents["claim-01"]["referenced_by"]["facts"] == ["fact-01"]
    assert ents["m-xt"]["referenced_by"]["params"] == ["p-xt"]
    assert ents["key2020"]["referenced_by"]["methods"] == ["m-xt"]
    assert ents["key2020"]["referenced_by"]["params"] == ["p-xt"]
    assert ents["key2020"]["referenced_by"]["claims"] == ["claim-02"]
    assert ents["fact-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert ents["p-xt"]["status"] == "draft"
    assert ents["p-xt"]["links"] == {"method": ["m-xt"], "note": ["key2020"]}


def test_card_links_forward_keeps_dangling(tmp_path):
    # links 保留真实落盘内容（悬空引用可见）；反向索引按目标存在性过滤
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-01", "data-ghost"],
                "statement": "悬空引用。", "supports": ["claim-ghost"],
                "status": "draft"})
    ents = client.get("/api/projects/demo/cards/links").json()["entities"]
    assert ents["fact-02"]["links"]["data"] == ["data-01", "data-ghost"]
    assert ents["fact-02"]["links"]["claim"] == ["claim-ghost"]
    assert "data-ghost" not in ents and "claim-ghost" not in ents
    assert ents["data-01"]["referenced_by"]["facts"] == ["fact-01", "fact-02"]


def test_card_links_keeps_duplicates(tmp_path):
    # 正向 links 原样透传落盘列表（含重复项）；referenced_by 去重排序形成对照
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "facts", "fact-04",
               {"id": "fact-04", "data": ["data-01", "data-01"],
                "statement": "重复引用。", "supports": [], "status": "draft"})
    ents = client.get("/api/projects/demo/cards/links").json()["entities"]
    assert ents["fact-04"]["links"]["data"] == ["data-01", "data-01"]
    assert ents["data-01"]["referenced_by"]["facts"] == ["fact-01", "fact-04"]


def test_card_links_includes_rejected(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "facts", "fact-03",
               {"id": "fact-03", "data": ["data-01"], "statement": "被否决。",
                "supports": [], "status": "rejected"})
    ents = client.get("/api/projects/demo/cards/links").json()["entities"]
    assert ents["fact-03"]["status"] == "rejected"
    assert ents["data-01"]["referenced_by"]["facts"] == ["fact-01", "fact-03"]


def test_card_links_route_precedes_kind(tmp_path):
    # /cards/links 必须先于 /cards/{kind} 注册（决策 L2），否则被当卡种名 404
    client, _ = make_client(tmp_path)
    assert client.get("/api/projects/demo/cards/links").status_code == 200
    assert client.get("/api/projects/demo/cards/bogus").status_code == 404


def test_card_links_unknown_project_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/api/projects/ghost/cards/links").status_code == 404

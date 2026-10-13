"""项目工作台导航数据（旧 subnav 的 API 化）：payload 携带各版块入口所需计数。

前端侧边栏（总览/叙事/卡片/图表/图谱/灵感/诊断）的显示/收缩完全由
dashboard payload 的 kind_counts/n_parts 驱动，服务端不再渲染导航 HTML。
"""
import shutil

from tests.webutil import make_client


def test_dashboard_payload_carries_navigation_counts(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo").json()
    assert set(payload["kind_counts"]) == {"data", "fact", "claim", "note",
                                           "method", "param"}
    assert payload["n_parts"] == 1                 # 叙事入口可见
    assert payload["kind_counts"]["data"] == 1     # 卡片 kind 分组入口可见
    # 待审队列条目带前端路由所需坐标
    client.post("/api/projects/demo/cards/fact/fact-01/status",
                json={"status": "draft", "comment": ""})
    queue = client.get("/api/projects/demo").json()["review_queue"]
    item = next(q for q in queue if q["id"] == "fact-01")
    assert item["type"] == "card" and item["card_kind"] == "fact" and item["rel"]


def test_narrative_absent_yields_parts_404(tmp_path):
    """无叙事 part：parts 列表 404（前端据此隐藏"叙事"入口）。"""
    client, projects = make_client(tmp_path)
    shutil.rmtree(projects / "demo" / "narrative")
    payload = client.get("/api/projects/demo").json()
    assert payload["n_parts"] == 0
    assert client.get("/api/projects/demo/parts").status_code == 404


def test_kind_counts_reflect_card_creation(tmp_path):
    client, root = make_client(tmp_path)
    from tests.helpers import write_card
    write_card(root / "demo" / "metadata" / "methods", "qpcr",
               {"id": "qpcr", "statement": "qPCR 三步法。", "protocol": "p",
                "status": "approved"})
    counts = client.get("/api/projects/demo").json()["kind_counts"]
    assert counts["method"] == 1


def test_review_queue_node_entries_carry_part_id(tmp_path):
    client, root = make_client(tmp_path)
    client.post("/api/projects/demo/parts/sec-01/nodes/para-01-01/status",
                json={"status": "draft"})
    queue = client.get("/api/projects/demo").json()["review_queue"]
    item = next(q for q in queue if q["id"] == "para-01-01")
    assert item["type"] == "node" and item["part_id"] == "sec-01"
    assert item["label"] == "叙事节点"

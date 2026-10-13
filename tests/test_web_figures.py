"""figures.yaml WebUI API 测试（webui figures 设计定案）。

夹具项目（webutil→helpers.make_minimal_project）：figures.yaml 含 fig-01
（caption 速率曲线、子图 a），data-01 refs=[fig-01a]，figures/fig-01a.png 存在。
"""
from tests.helpers import write_yaml
from tests.webutil import make_client


def test_figures_list_rows(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo/figures").json()
    assert payload["load_error"] is None
    row = payload["rows"][0]
    assert row["key"] == "fig-01" and row["caption"] == "速率曲线"
    assert row["kind"] == "figure" and row["used_by"] == ["data-01"]
    assert row["file_missing"] is False and row["unused"] is False


def test_figures_list_markers(tmp_path):
    client, projects = make_client(tmp_path)
    write_yaml(projects / "demo" / "metadata" / "figures.yaml",
               {"fig-01": {"caption": "速率曲线", "subfigs": {"a": "60°C"}},
                "fig-02": {"caption": "没人用的图"}})
    rows = {r["key"]: r for r in
            client.get("/api/projects/demo/figures").json()["rows"]}
    assert rows["fig-02"]["file_missing"] is True    # fig-02 无 png/pdf
    assert rows["fig-02"]["unused"] is True          # 无 data 卡引用 fig-02


def test_figures_unknown_project_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/api/projects/nope/figures").status_code == 404


def test_broken_yaml_list_viewable_readonly(tmp_path):
    """F3：figures.yaml 坏 → 列表仍 200，load_error 指认 E-FIG-LOAD（前端转只读）。"""
    client, projects = make_client(tmp_path)
    (projects / "demo" / "metadata" / "figures.yaml").write_text(
        "fig-01: [unclosed\n", encoding="utf-8")
    payload = client.get("/api/projects/demo/figures").json()
    assert payload["rows"] == []
    assert "E-FIG-LOAD" in payload["load_error"]


def _yaml_path(projects):
    return projects / "demo" / "metadata" / "figures.yaml"


def test_figure_new_auto_number(tmp_path):
    client, projects = make_client(tmp_path)
    resp = client.post("/api/projects/demo/figures",
                       json={"prefix": "fig", "key": "", "caption": "新图",
                             "subfigs": "a: 左"})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    text = _yaml_path(projects).read_text(encoding="utf-8")
    assert "fig-02:" in text and "新图" in text


def test_figure_new_explicit_key(tmp_path):
    client, projects = make_client(tmp_path)
    resp = client.post("/api/projects/demo/figures",
                       json={"prefix": "tbl", "key": "tbl-01", "caption": "表一",
                             "subfigs": ""})
    assert resp.status_code == 200
    assert "tbl-01:" in _yaml_path(projects).read_text(encoding="utf-8")


def test_figure_new_collision_echoes_key(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/api/projects/demo/figures",
                       json={"prefix": "fig", "key": "fig-01", "caption": "x",
                             "subfigs": ""})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "E-FIG-COLLISION"
    assert body["values"]["key"] == "fig-01"   # 键名保真（F8：键是身份）


def test_figure_new_invalid_name(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/api/projects/demo/figures",
                       json={"prefix": "fig", "key": "a/b", "caption": "x",
                             "subfigs": ""})
    assert resp.status_code == 422 and resp.json()["code"] == "E-FIG-NAME"


def test_figure_get_prefills(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo/figures/fig-01").json()
    assert payload["values"]["caption"] == "速率曲线"
    assert payload["values"]["subfigs"] == "a: 60°C"


def test_figure_edit_keeps_order(tmp_path):
    client, projects = make_client(tmp_path)
    write_yaml(_yaml_path(projects),
               {"fig-01": {"caption": "速率曲线", "subfigs": {"a": "60°C"}},
                "fig-02": {"caption": "第二张"}})
    resp = client.patch("/api/projects/demo/figures/fig-01",
                        json={"caption": "改过的题注", "subfigs": "b: 右"})
    assert resp.status_code == 200
    text = _yaml_path(projects).read_text(encoding="utf-8")
    assert text.index("fig-01:") < text.index("fig-02:")   # 键序保持
    assert "改过的题注" in text and "b: 右" in text


def test_figure_delete_ok(tmp_path):
    client, projects = make_client(tmp_path)
    write_yaml(_yaml_path(projects),
               {"fig-01": {"caption": "速率曲线", "subfigs": {"a": "60°C"}},
                "fig-02": {"caption": "没人用"}})
    resp = client.post("/api/projects/demo/figures/fig-02/delete")
    assert resp.status_code == 200 and resp.json()["ok"] is True
    text = _yaml_path(projects).read_text(encoding="utf-8")
    assert "fig-02" not in text and "fig-01:" in text


def test_figure_delete_blocked_in_use(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/api/projects/demo/figures/fig-01/delete")
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "E-FIG-IN-USE" and "data-01" in body["detail"]


def test_figure_delete_refused_on_degraded_project(tmp_path):
    """F6 从严：figures.yaml 健康、项目带病（project=None）→ 删除拒绝（引用检查
    需要完整 data 卡视图）。"""
    client, projects = make_client(tmp_path)
    (projects / "demo" / "metadata" / "data" / "data-01.md").write_text(
        "not: [valid", encoding="utf-8")
    resp = client.post("/api/projects/demo/figures/fig-01/delete")
    assert resp.status_code == 422
    assert "删除需要完整引用检查" in resp.json()["detail"]
    assert "fig-01:" in _yaml_path(projects).read_text(encoding="utf-8")


def test_figure_get_refused_on_broken_yaml(tmp_path):
    """E-FIG-LOAD 时详情 GET 也 422（前端据此转只读列表）。"""
    client, projects = make_client(tmp_path)
    _yaml_path(projects).write_text("fig-01: [unclosed\n", encoding="utf-8")
    resp = client.get("/api/projects/demo/figures/fig-01")
    assert resp.status_code == 422
    assert resp.json()["code"] == "E-FIG-LOAD"


def test_write_ops_refused_on_broken_yaml(tmp_path):
    """F3 后半：figures.yaml 坏 → 一切写操作 422 回 E-FIG-LOAD。"""
    client, projects = make_client(tmp_path)
    _yaml_path(projects).write_text("fig-01: [unclosed\n", encoding="utf-8")
    assert client.post("/api/projects/demo/figures",
                       json={"prefix": "fig", "key": "", "caption": "x",
                             "subfigs": ""}).status_code == 422
    assert client.patch("/api/projects/demo/figures/fig-01",
                        json={"caption": "x", "subfigs": ""}).status_code == 422
    assert client.post("/api/projects/demo/figures/fig-01/delete").status_code == 422

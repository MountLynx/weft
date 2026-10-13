"""WebUI 骨架（SPA 宿主 + API 挂载）与 serve 子命令。"""
import pytest

pytest.importorskip("fastapi")

from pathlib import Path

from fastapi.testclient import TestClient
from tests.helpers import make_minimal_project
from typer.testing import CliRunner

import weft.cli as cli_mod
from weft.web import create_app


def test_create_app_health(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/healthz").json() == {"ok": True}


def test_shell_served_and_api_unknown_404(tmp_path: Path):
    """GET / 返回 SPA shell（text/html）；/api 与 /static 未知路径保持 JSON 404。"""
    client = TestClient(create_app(tmp_path))
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "weft-theme" in resp.text                    # 防闪脚本随 shell 走
    assert client.get("/p/demo/dashboard").status_code == 200   # 前端路由路径交 shell
    r404 = client.get("/api/nope")
    assert r404.status_code == 404
    assert r404.headers["content-type"].startswith("application/json")
    # docs/openapi 均禁用：/docs、/openapi.json 无 FastAPI 文档内容（落 SPA 宿主）
    assert "swagger" not in client.get("/docs").text.lower()
    assert '"openapi"' not in client.get("/openapi.json").text


def test_serve_invokes_uvicorn(tmp_path: Path, monkeypatch):
    import uvicorn

    captured = {}

    def fake_run(app, host=None, port=None):
        captured["host"], captured["port"], captured["app"] = host, port, app

    monkeypatch.setattr(uvicorn, "run", fake_run)
    projects = tmp_path / "projects"
    make_minimal_project(projects / "demo")
    result = CliRunner().invoke(
        cli_mod.app, ["serve", str(projects), "--host", "127.0.0.1", "--port", "8123"])
    assert result.exit_code == 0
    assert captured["port"] == 8123 and captured["host"] == "127.0.0.1"
    assert captured["app"].state.projects_root == projects.resolve()


def test_serve_rejects_missing_root(tmp_path: Path, monkeypatch):
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("uvicorn.run 不应被调用")))
    result = CliRunner().invoke(
        cli_mod.app, ["serve", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "项目根目录不存在" in result.output

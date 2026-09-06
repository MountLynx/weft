"""WebUI 骨架与 serve 子命令。"""
from pathlib import Path

from fastapi.testclient import TestClient
from tests.helpers import make_minimal_project
from typer.testing import CliRunner

import weft.cli as cli_mod
from weft.web import create_app


def test_create_app_health(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/healthz").json() == {"ok": True}


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

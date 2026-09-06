"""WebUI 测试夹具：tmp projects 根 + TestClient。"""
from pathlib import Path

from fastapi.testclient import TestClient

from tests.helpers import make_minimal_project
from weft.web import create_app


def make_client(tmp_path: Path) -> tuple[TestClient, Path]:
    projects = tmp_path / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    make_minimal_project(projects / "demo")
    return TestClient(create_app(projects)), projects

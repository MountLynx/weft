"""weft WebUI（webui 设计 §1）：weft 公共 API 之上的 FastAPI 薄壳。

分层红线：本包不得 import module_harness / llm（红线 1）；生成一律经 weft.engine 公共 API。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(projects_root: Path | None = None,
               *, use_registry: bool = False) -> FastAPI:
    """两模式（projects registry 设计 §5）：注册表模式（use_registry=True）与扫描模式。

    - use_registry=True：项目清单来自全局注册表（weft serve 无参时），pid = 注册名。
    - projects_root：扫描模式（现状），每请求扫描根下一级子目录，pid = 目录名。
    """
    app = FastAPI(title="weft WebUI", docs_url=None, redoc_url=None)
    if use_registry:
        app.state.projects_source = "registry"
        app.state.projects_root = None
    else:
        if projects_root is None:
            raise ValueError("create_app 需要 projects_root 或 use_registry=True")
        app.state.projects_source = "scan"
        app.state.projects_root = Path(projects_root).resolve()
    from weft.web.runs import RunManager

    app.state.runs = RunManager()
    from weft.web.routes import register_all

    register_all(app)
    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app

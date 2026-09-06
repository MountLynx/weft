"""weft WebUI（webui 设计 §1）：weft 公共 API 之上的 FastAPI 薄壳。

分层红线：本包不得 import module_harness / llm（红线 1）；生成一律经 weft.engine 公共 API。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(projects_root: Path) -> FastAPI:
    app = FastAPI(title="weft WebUI", docs_url=None, redoc_url=None)
    app.state.projects_root = Path(projects_root).resolve()
    from weft.web.routes import register_all

    register_all(app)
    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app

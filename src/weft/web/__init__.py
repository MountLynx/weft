"""weft WebUI（webui-react 设计 §1）：weft 公共 API 之上的 FastAPI 薄壳。

分层红线：本包不得 import module_harness / llm（红线 1）；生成一律经 weft.engine 公共 API。
JSON API（/api/*）+ React SPA 静态宿主（构建产物 static/app/，提交入库，运行时零 Node）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

_STATIC_DIR = Path(__file__).parent / "static"
_APP_INDEX = _STATIC_DIR / "app" / "index.html"


def create_app(projects_root: Path | None = None,
               *, use_registry: bool = False) -> FastAPI:
    """两模式（projects registry 设计 §5）：注册表模式（use_registry=True）与扫描模式。

    - use_registry=True：项目清单来自全局注册表（weft serve 无参时），pid = 注册名。
    - projects_root：扫描模式（现状），每请求扫描根下一级子目录，pid = 目录名。
    """
    app = FastAPI(title="weft WebUI", docs_url=None, redoc_url=None,
                  openapi_url=None)
    if use_registry:
        app.state.projects_source = "registry"
        app.state.projects_root = None
    else:
        if projects_root is None:
            raise ValueError("create_app 需要 projects_root 或 use_registry=True")
        app.state.projects_source = "scan"
        app.state.projects_root = Path(projects_root).resolve()

    from weft.web.api import register_all
    from weft.web.runs import RunManager

    app.state.runs = RunManager()
    register_all(app)
    # html=True：/static/app/ 目录访问回落到该目录的 index.html（SPA 外壳）
    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR, html=True),
                  name="static")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_host(full_path: str):
        # API/静态未知路径保持 JSON 404；其余 GET（含 /）一律交前端路由（BrowserRouter）
        if full_path.startswith(("api/", "static/", "healthz")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if not _APP_INDEX.is_file():
            return JSONResponse(
                {"detail": "SPA 未构建：先在 webui/ 目录执行 pnpm build"},
                status_code=503)
        return FileResponse(_APP_INDEX, headers={"Cache-Control": "no-cache"})

    return app

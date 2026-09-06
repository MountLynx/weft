"""路由注册中心（webui 设计 §3）。"""
from __future__ import annotations

from fastapi import FastAPI


def register_all(app: FastAPI) -> None:
    from weft.web.routes import core

    core.register(app)

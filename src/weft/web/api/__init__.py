"""JSON API 路由包（webui-react 设计 §3）：替代旧 routes/ 的 HTML 路由。"""
from __future__ import annotations

from fastapi import FastAPI


def register_all(app: FastAPI) -> None:
    from weft.web.api import cards, figures, inspire, parts, projects

    for module in (projects, cards, parts, figures, inspire):
        module.register(app)

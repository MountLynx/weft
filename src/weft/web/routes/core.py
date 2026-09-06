"""核心页面路由：项目列表 / 项目总览 / graph / 诊断 / 文件预览。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


def register(app) -> None:
    app.include_router(router)

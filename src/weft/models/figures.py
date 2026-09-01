"""图注层模型（spec §3.6，metadata/figures.yaml）。"""
from pydantic import BaseModel


class FigureEntry(BaseModel):
    """人工直接维护、无 status；解析宽松：未知键忽略，caption/subfigs 可缺省。"""

    caption: str = ""
    subfigs: dict[str, str] = {}

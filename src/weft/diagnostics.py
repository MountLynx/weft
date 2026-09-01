"""诊断消息：store / validation / graphgen / cli 共用的唯一消息类型。

定位粒度 = 文件 + 字段（spec §4），path 为相对项目根的 posix 风格路径。
"""
from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    level: Level
    code: str          # 稳定标识，如 "E-DANGLING-REF"（见计划诊断码总表）
    path: str          # 相对项目根路径；全局性消息用 "."
    field: str | None  # 出错的字段名，可空
    message: str

    @property
    def is_error(self) -> bool:
        return self.level is Level.ERROR

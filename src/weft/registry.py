"""全局项目注册表（projects registry 设计 §3）：多项目共存的唯一项目清单。

单一状态文件 $WEFT_HOME/projects.json（缺省 ~/.weft/），项目可在磁盘任意位置；
注册名是全局唯一 id（= WebUI pid）。损坏 fail-closed（E-REG-MALFORMED），
不静默重建；名称/路径双唯一保证 WebUI 路由无歧义。
本模块不 import llm/module_harness（红线 1）；模型不进 models/（卡片 schema 冻结）。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from weft.diagnostics import Diagnostic, Level

REGISTRY_VERSION = 1
REGISTRY_FILENAME = "projects.json"


class RegistryError(Exception):
    """注册表操作失败；携带诊断码，CLI/WebUI 经 diagnostic() 统一呈现。"""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(message)

    def diagnostic(self) -> Diagnostic:
        return Diagnostic(Level.ERROR, self.code, self.path, None, self.message)


# ---------- 名称校验（WebUI 与 CLI 共享的唯一实现） ----------

# 项目名 = 用户可控的落盘路径组件与 URL pid，只能在此守卫（同 cards.py 的 _CARD_ID_RE 先例）
_NAME_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WINDOWS_RESERVED = ({"CON", "PRN", "AUX", "NUL"}
                     | {f"COM{i}" for i in range(1, 10)}
                     | {f"LPT{i}" for i in range(1, 10)})


def validate_project_name(raw: str) -> tuple[str, str | None]:
    """返回（规范名 = 去首尾空白, 错误信息）；黑名单制允许中文等任意安全字符。"""
    name = raw.strip()
    if not name:
        return "", "项目名不能为空"
    if name in (".", "..") or name.startswith("."):
        return name, "项目名不能以 . 开头（避免与工具目录约定冲突）"
    if name.endswith("."):
        return name, "项目名不能以 . 结尾（Windows 会静默剥离，导致访问不到）"
    if _NAME_ILLEGAL_RE.search(name):
        return name, "项目名含非法字符（不允许 \\ / : * ? \" < > | 及控制字符）"
    if name.upper() in _WINDOWS_RESERVED:
        return name, "项目名是 Windows 保留设备名"
    if len(name) > 100:
        return name, "项目名过长（不超过 100 字符）"
    return name, None


# ---------- 数据模型 ----------

class RegistryEntry(BaseModel):
    name: str
    path: str          # Path.resolve().as_posix()，绝对路径正斜杠
    registered_at: str  # 本地时间 ISO 8601（秒精度）


class RegistryData(BaseModel):
    version: int = REGISTRY_VERSION
    default_root: str | None = None
    projects: list[RegistryEntry] = []

    model_config = {"extra": "forbid"}


# ---------- 读写 ----------

def registry_path() -> Path:
    """注册表文件位置；WEFT_HOME 重定向是测试隔离与云端部署的适配点。"""
    env_home = os.environ.get("WEFT_HOME")
    base = Path(env_home) if env_home else Path.home() / ".weft"
    return base / REGISTRY_FILENAME


def load_registry(path: Path | None = None) -> RegistryData:
    """读注册表；文件不存在 = 空表（合法初态），损坏/结构不符 fail-closed。"""
    target = path if path is not None else registry_path()
    if not target.exists():
        return RegistryData()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError("E-REG-MALFORMED", str(target),
                            f"注册表不可读或非法 JSON：{exc}") from exc
    try:
        data = RegistryData.model_validate(raw)
    except ValidationError as exc:
        raise RegistryError("E-REG-MALFORMED", str(target),
                            f"注册表结构不符：{exc}") from exc
    if data.version > REGISTRY_VERSION:
        raise RegistryError("E-REG-MALFORMED", str(target),
                            f"注册表版本过新（{data.version} > {REGISTRY_VERSION}），"
                            "请升级 weft")
    if data.version < REGISTRY_VERSION:
        raise RegistryError("E-REG-MALFORMED", str(target),
                            f"注册表版本过旧（{data.version} < {REGISTRY_VERSION}）")
    return data


def save_registry(data: RegistryData, path: Path | None = None) -> Path:
    """原子写（tmp + os.replace）；UTF-8、indent 2、LF、中文原样。"""
    target = path if path is not None else registry_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data.model_dump(), ensure_ascii=False, indent=2) + "\n"
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, target)
    return target


# ---------- 条目操作（全部零副作用失败：失败时绝不改表） ----------

def _check_registrable(reg: RegistryData, clean: str, posix: str) -> None:
    for existing in reg.projects:
        if existing.name == clean:
            raise RegistryError("E-REG-DUP", clean,
                                f"注册名已存在：{clean}（{existing.path}）")
        if existing.path == posix:
            raise RegistryError("E-REG-PATH-DUP", posix,
                                f"该路径已用名称 {existing.name} 登记")


def ensure_registrable(reg: RegistryData, name: str, path: Path) -> str:
    """落盘前预检：名称校验 + 双唯一；返回规范名，失败抛 RegistryError（零写入）。"""
    clean, err = validate_project_name(name)
    if err is not None:
        raise RegistryError("E-REG-NAME", name, err)
    _check_registrable(reg, clean, path.resolve().as_posix())
    return clean


def register_project(reg: RegistryData, name: str, path: Path) -> RegistryEntry:
    """校验并追加条目（预检 + 登记；失败时表不变）。"""
    clean, err = validate_project_name(name)
    if err is not None:
        raise RegistryError("E-REG-NAME", name, err)
    posix = path.resolve().as_posix()
    _check_registrable(reg, clean, posix)
    entry = RegistryEntry(name=clean, path=posix,
                          registered_at=datetime.now().isoformat(timespec="seconds"))
    reg.projects.append(entry)
    return entry


def unregister_project(reg: RegistryData, name: str) -> RegistryEntry:
    """只摘表：返回被摘除的条目；本地文件是否存在与本函数无关。"""
    for index, existing in enumerate(reg.projects):
        if existing.name == name:
            return reg.projects.pop(index)
    raise RegistryError("E-REG-UNKNOWN", name, f"未注册的项目名：{name}")


def resolve_default_root(reg: RegistryData, home: Path | None = None) -> Path:
    """`new` 位置回退链的末两级：default_root > <home>/weft-projects。"""
    if reg.default_root:
        return Path(reg.default_root)
    base = home if home is not None else Path.home()
    return base / "weft-projects"

"""分层守卫（spec §5）：engine/ 是 src 内唯一 import specmodule（llm/module_harness）的层。

防分层腐化：engine/ 之外的 src 模块出现对 specmodule 包的 import 即失败。
tests/ 不在扫描范围（测试基建可 import llm.client 构造假响应）。
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "weft"

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(llm|module_harness)\b", re.MULTILINE)


def test_only_engine_imports_specmodule():
    offenders = [
        py.relative_to(SRC).as_posix()
        for py in SRC.rglob("*.py")
        if not py.relative_to(SRC).as_posix().startswith("engine/")
        and _IMPORT_RE.search(py.read_text(encoding="utf-8"))
    ]
    assert offenders == []

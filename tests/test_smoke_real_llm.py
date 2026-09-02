"""真实 LLM 冒烟（spec §11）：默认排除。

运行（用户指示：LLM 配置用 SpecModule 目录的 config.json + .env）：
    set WEFT_SMOKE_LLM=1 && .venv/Scripts/python -m pytest tests -m smoke -v
"""
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from weft.cli import app

pytestmark = pytest.mark.smoke
runner = CliRunner()
SAMPLE = Path(__file__).parent.parent / "examples" / "paper-demo"
SPECMODULE = Path(r"C:/Users/xingy/Desktop/开发/SpecModule")


@pytest.mark.skipif(not os.environ.get("WEFT_SMOKE_LLM"),
                    reason="设 WEFT_SMOKE_LLM=1 并配置 LLM 环境变量后才真正调用")
def test_real_llm_drafts_sec04(tmp_path):
    work = tmp_path / "proj"
    shutil.copytree(SAMPLE, work)
    for name in ("config.json", ".env"):   # 用户提供：LLM 配置在 SpecModule 目录
        src = SPECMODULE / name
        if src.exists():
            shutil.copy(src, work / name)
    result = runner.invoke(app, ["draft", "sec-04", str(work)])
    assert result.exit_code == 0, result.output
    draft = (work / "drafts" / "sec-04.md").read_text(encoding="utf-8")
    assert "<!-- weft:node=para-04-01" in draft
    assert len(draft.strip()) > 100        # 真实行文而非 mock 占位

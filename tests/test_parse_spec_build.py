"""parse spec_build：双模式 prompt 分叉、flow 单边、view 注入、key 前置。"""
import pytest

from weft.engine.parse.spec_build import build_parse_tasklist

DIGEST = "== fact ==\nfact-01 | approved | 温度提高速率。"


def _tasklist(**kwargs):
    kwargs.setdefault("text", "一篇测试文章。")
    kwargs.setdefault("digest", DIGEST)
    return build_parse_tasklist(**kwargs)


def test_flow_single_edge_per_line_and_chain_order():
    tl = _tasklist(mode="decompose")
    assert set(tl.tasks) == {"p01", "p02", "p03", "p04", "p05"}
    assert tl.flow.splitlines() == ["[p01] --> p02", "p02 --> p03",
                                    "p03 --> p04", "p04 --> p05"]


def test_view_inputs_wiring():
    tl = _tasklist(mode="decompose")
    assert tl.tasks["p03"].inputs == {"p02": "p02"}
    assert tl.tasks["p04"].inputs == {"p02": "p02", "p03": "p03"}
    assert tl.tasks["p05"].inputs == {"p02": "p02"}


def test_literature_mode_prompts():
    tl = _tasklist(mode="literature", bib_key="smith2024")
    assert "summary" in tl.tasks["p02"].prompt          # 摘要折进 P2
    assert '"note"' in tl.tasks["p03"].prompt           # note 三档判定指令
    assert "unchanged" in tl.tasks["p03"].prompt
    assert "smith2024" in tl.tasks["p03"].prompt        # note 判定可对照正确 note 卡
    assert '"smith2024"' in tl.tasks["p04"].prompt      # 次级引用默认值注入
    assert "{bibkey}" not in tl.tasks["p04"].prompt     # 模板替换无残留


def test_decompose_mode_prompts():
    tl = _tasklist(mode="decompose")
    assert "summary" not in tl.tasks["p02"].prompt
    assert '"note"' not in tl.tasks["p03"].prompt
    assert "note/bib key" in tl.tasks["p04"].prompt     # 同 inspire 的匹配规则
    assert "最贴切 claim" in tl.tasks["p04"].prompt     # [@key] 归属条款同 inspire


def test_literature_requires_bib_key():
    with pytest.raises(ValueError, match="bib_key"):
        _tasklist(mode="literature")


def test_literature_extract_schema_mentions_entry():
    from weft.engine.parse.spec_build import _EXTRACT_LITERATURE_SCHEMA
    assert '"entry"' in _EXTRACT_LITERATURE_SCHEMA


def test_decompose_extract_schema_omits_entry():
    from weft.engine.parse.spec_build import _EXTRACT_DECOMPOSE_SCHEMA
    assert '"entry"' not in _EXTRACT_DECOMPOSE_SCHEMA

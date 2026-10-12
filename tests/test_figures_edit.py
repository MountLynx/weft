"""figures_edit 引擎单测（webui figures 设计定案，决策 F1–F12）。"""
import pytest

from weft.figures_edit import (
    FiguresEditError,
    add_entry,
    ensure_figure_key,
    load_for_edit,
    next_figure_key,
)
from weft.models.figures import FigureEntry
from weft.scaffold import NewNameError, _ensure_component


def _write_yaml(root, text: str) -> None:
    (root / "metadata").mkdir(parents=True, exist_ok=True)
    (root / "metadata" / "figures.yaml").write_text(text, encoding="utf-8")


def test_load_missing_returns_empty(tmp_path):
    assert load_for_edit(tmp_path) == {}


def test_load_parses_in_key_order(tmp_path):
    _write_yaml(tmp_path,
                "fig-02:\n  caption: 第二张\n"
                "fig-01:\n  caption: 第一张\n  subfigs:\n    a: 左\n")
    entries = load_for_edit(tmp_path)
    assert list(entries) == ["fig-02", "fig-01"]
    assert entries["fig-01"].caption == "第一张"
    assert entries["fig-01"].subfigs == {"a": "左"}


def test_load_rejects_top_level_list(tmp_path):
    _write_yaml(tmp_path, "- a\n- b\n")
    with pytest.raises(FiguresEditError) as excinfo:
        load_for_edit(tmp_path)
    assert excinfo.value.code == "E-FIG-LOAD"


def test_load_rejects_bad_entry(tmp_path):
    _write_yaml(tmp_path, "fig-01:\n  caption: 1\n  subfigs: not-a-map\n")
    with pytest.raises(FiguresEditError) as excinfo:
        load_for_edit(tmp_path)
    assert excinfo.value.code == "E-FIG-LOAD"
    assert "fig-01" in excinfo.value.message


def test_load_rejects_malformed_yaml(tmp_path):
    _write_yaml(tmp_path, "fig-01: [unclosed\n")
    with pytest.raises(FiguresEditError) as excinfo:
        load_for_edit(tmp_path)
    assert excinfo.value.code == "E-FIG-LOAD"


def test_load_rejects_undecodable_bytes(tmp_path):
    _write_yaml(tmp_path, "")
    (tmp_path / "metadata" / "figures.yaml").write_bytes(
        "fig-01:\n  caption: 速率\n".encode("gbk"))
    with pytest.raises(FiguresEditError) as excinfo:
        load_for_edit(tmp_path)
    assert excinfo.value.code == "E-FIG-LOAD"


VALID_KEYS = ["fig-01", "tbl-1", "x", "a-b-c", "中文图", "fig_01.v2"]
INVALID_KEYS = ["", "  x", "x  ", ".", "..", "a/b", "a\\b", "a:b", 'a"b',
                "a<b", "a|b", "a?b", "a*b", "a\nb", ".hidden", "x."]


def test_next_figure_key_from_existing():
    entries = {"fig-01": FigureEntry(), "fig-04": FigureEntry()}
    assert next_figure_key(entries, "fig-") == "fig-05"


def test_next_figure_key_ignores_suffix_and_other_prefix():
    entries = {"fig-01a": FigureEntry(), "tbl-02": FigureEntry(),
               "fig-intro": FigureEntry()}
    assert next_figure_key(entries, "fig-") == "fig-01"
    assert next_figure_key({}, "tbl-") == "tbl-01"


@pytest.mark.parametrize("value", VALID_KEYS)
def test_ensure_figure_key_accepts_safe(value):
    ensure_figure_key(value)  # 不抛即通过


@pytest.mark.parametrize("value", INVALID_KEYS)
def test_ensure_figure_key_rejects_unsafe(value):
    with pytest.raises(FiguresEditError) as excinfo:
        ensure_figure_key(value)
    assert excinfo.value.code == "E-FIG-NAME"


@pytest.mark.parametrize("value", VALID_KEYS + INVALID_KEYS)
def test_ensure_figure_key_matches_scaffold_rule(value):
    """F4：与 weft new 的 _ensure_component（N9）规则一致，样本集守卫。"""
    try:
        ensure_figure_key(value)
        ours = True
    except FiguresEditError:
        ours = False
    try:
        _ensure_component("key", value)
        theirs = True
    except NewNameError:
        theirs = False
    assert ours == theirs


def test_add_entry_explicit():
    entries = {"fig-01": FigureEntry(caption="旧")}
    out = add_entry(entries, "fig-02", "新图", {"a": "左"}, "fig-")
    assert list(out) == ["fig-01", "fig-02"]
    assert out["fig-02"].caption == "新图"
    assert out["fig-01"].caption == "旧"          # 原映射不被就地修改


def test_add_entry_auto_number():
    entries = {"fig-01": FigureEntry()}
    out = add_entry(entries, "", "自动", {}, "fig-")
    assert "fig-02" in out


def test_add_entry_collision():
    with pytest.raises(FiguresEditError) as excinfo:
        add_entry({"fig-01": FigureEntry()}, "fig-01", "x", {}, "fig-")
    assert excinfo.value.code == "E-FIG-COLLISION"


def test_add_entry_appends_tail():
    """键序即 assemble 编号：新键必须排尾部（F5）。"""
    entries = {"fig-03": FigureEntry(), "fig-01": FigureEntry()}
    out = add_entry(entries, "fig-09", "x", {}, "fig-")
    assert list(out) == ["fig-03", "fig-01", "fig-09"]

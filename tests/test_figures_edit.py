"""figures_edit 引擎单测（webui figures 设计定案，决策 F1–F12）。"""
import pytest

from weft.figures_edit import (
    FiguresEditError,
    add_entry,
    ensure_figure_key,
    load_for_edit,
    next_figure_key,
    parse_subfigs,
    remove_entry,
    update_entry,
    write_figures_yaml,
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


def test_parse_subfigs_basic():
    assert parse_subfigs("a: 60°C\nb: 温度: 95% CI\n\n") == \
        {"a": "60°C", "b": "温度: 95% CI"}      # 首个冒号切分，空行跳过


@pytest.mark.parametrize("text", ["没有冒号", ": 说明", "a b: 说明", "   : x"])
def test_parse_subfigs_invalid(text):
    with pytest.raises(FiguresEditError) as excinfo:
        parse_subfigs(text)
    assert excinfo.value.code == "E-FIG-VALUE"


def test_update_entry_keeps_order():
    entries = {"fig-01": FigureEntry(caption="旧"), "fig-02": FigureEntry()}
    out = update_entry(entries, "fig-01", "新", {"b": "右"})
    assert list(out) == ["fig-01", "fig-02"]
    assert out["fig-01"].caption == "新"
    assert out["fig-01"].subfigs == {"b": "右"}


def test_update_entry_missing():
    with pytest.raises(FiguresEditError) as excinfo:
        update_entry({}, "fig-01", "x", {})
    assert excinfo.value.code == "E-FIG-COLLISION"


def test_remove_entry_ok():
    entries = {"fig-01": FigureEntry(), "fig-02": FigureEntry()}
    out = remove_entry(entries, "fig-01", {"data-01": {"fig-02"}})
    assert list(out) == ["fig-02"]


def test_remove_entry_blocked_direct():
    entries = {"fig-01": FigureEntry()}
    with pytest.raises(FiguresEditError) as excinfo:
        remove_entry(entries, "fig-01", {"data-01": {"fig-01"}})
    assert excinfo.value.code == "E-FIG-IN-USE"
    assert "data-01" in excinfo.value.message


def test_remove_entry_blocked_via_subfig():
    entries = {"fig-01": FigureEntry(subfigs={"a": "左"})}
    with pytest.raises(FiguresEditError) as excinfo:
        remove_entry(entries, "fig-01", {"data-01": {"fig-01a"}})
    assert excinfo.value.code == "E-FIG-IN-USE"


def test_remove_entry_blocked_rejected_card():
    """F6：rejected 卡也算引用——可能被重新批准，删除从严。"""
    entries = {"fig-01": FigureEntry()}
    with pytest.raises(FiguresEditError) as excinfo:
        remove_entry(entries, "fig-01", {"data-09": {"fig-01"}})
    assert excinfo.value.code == "E-FIG-IN-USE"


def test_remove_entry_missing():
    with pytest.raises(FiguresEditError) as excinfo:
        remove_entry({}, "fig-01", {})
    assert excinfo.value.code == "E-FIG-COLLISION"


def test_write_roundtrip_defaults_omitted(tmp_path):
    entries = {"fig-01": FigureEntry(caption="速率", subfigs={"a": "左"}),
               "fig-02": FigureEntry()}
    write_figures_yaml(tmp_path, entries)
    loaded = load_for_edit(tmp_path)
    assert loaded == entries
    assert list(loaded) == list(entries)             # 键序即 assemble 编号（F5）
    text = (tmp_path / "metadata" / "figures.yaml").read_text(encoding="utf-8")
    assert "fig-02:\n" in text and "fig-02:\n  caption" not in text  # 空条目裸键


def test_write_deterministic_lf(tmp_path):
    entries = {"fig-01": FigureEntry(caption="a"), "fig-02": FigureEntry()}
    p1 = write_figures_yaml(tmp_path, entries)
    b1 = p1.read_bytes()
    p2 = write_figures_yaml(tmp_path, entries)
    assert p2.read_bytes() == b1                     # 字节级确定（黄金可比对）
    assert b"\r" not in b1 and b1.endswith(b"\n")


def test_write_quotes_special_caption(tmp_path):
    entries = {"fig-01": FigureEntry(caption="速率: 95% CI")}
    write_figures_yaml(tmp_path, entries)
    assert load_for_edit(tmp_path)["fig-01"].caption == "速率: 95% CI"


@pytest.mark.parametrize("caption", ["123", "true", "on", "null", "007"])
def test_write_quotes_rescalarizable_caption(tmp_path, caption):
    """裸写会被 YAML 重定型为 int/bool/None → E-FIG-LOAD 锁死注册表，必须加引号。"""
    entries = {"fig-01": FigureEntry(caption=caption)}
    write_figures_yaml(tmp_path, entries)
    text = (tmp_path / "metadata" / "figures.yaml").read_text(encoding="utf-8")
    assert load_for_edit(tmp_path)["fig-01"].caption == caption
    assert f'"{caption}"' in text  # 落盘带引号


def test_write_quotes_numeric_subfig_key(tmp_path):
    """parse_subfigs 放行数字子图号（最自然的输入），落盘同样不得重定型。"""
    entries = {"fig-01": FigureEntry(subfigs={"1": "60°C"})}
    write_figures_yaml(tmp_path, entries)
    assert load_for_edit(tmp_path)["fig-01"].subfigs == {"1": "60°C"}


def test_write_empty_entries_roundtrip(tmp_path):
    p = write_figures_yaml(tmp_path, {})
    assert p.read_bytes() == b""
    assert load_for_edit(tmp_path) == {}


def test_load_normalizes_crlf(tmp_path):
    _write_yaml(tmp_path, "")
    (tmp_path / "metadata" / "figures.yaml").write_bytes(
        "fig-01:\r\n  caption: 速率\r\n".encode("utf-8"))
    assert load_for_edit(tmp_path)["fig-01"].caption == "速率"

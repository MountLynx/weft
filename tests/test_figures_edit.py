"""figures_edit 引擎单测（webui figures 设计定案，决策 F1–F12）。"""
import pytest

from weft.figures_edit import (
    FiguresEditError,
    load_for_edit,
)


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

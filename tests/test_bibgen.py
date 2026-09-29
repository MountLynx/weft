"""bibgen 单测：确定性渲染（bibgen 设计 §5）+ key minting（§6）。"""
import pytest

from tests.helpers import build_project
from weft import bibgen
from weft.models.cards import NoteCard

EXPECTED = """\
% ----------------------------------------------------------
% 此文件由 weft 自动生成（weft.yaml: bib.managed = true）。
% 真源：metadata/notes/ 中 status: approved 且带 entry 的文献卡。
% 请勿手改——手改内容会在下次同步时丢失。新增文献请建文献卡。
% ----------------------------------------------------------

@article{smith2020,
  title = {Thermally activated catalysis},
  author = {Smith, Jane and Lee, Kyung},
  year = {2020},
  journal = {Journal of Thermal Chemistry},
  volume = {12},
  pages = {45--58}
}

@misc{x2021,
  title = {X},
  year = {2021},
  note = {预印本}
}
"""


def _note(nid, status="approved", entry=None):
    meta = {"id": nid, "status": status}
    if entry is not None:
        meta["entry"] = entry
    return NoteCard.model_validate(meta)


def test_render_bib_golden_sorted_deterministic():
    project = build_project(notes=[
        _note("x2021", entry={"type": "misc", "title": "X", "year": 2021,
                              "fields": {"note": "预印本"}}),
        _note("smith2020", entry={
            "type": "article", "title": "Thermally activated catalysis",
            "author": ["Smith, Jane", "Lee, Kyung"], "year": 2020,
            "journal": "Journal of Thermal Chemistry", "volume": "12",
            "pages": "45--58"}),
    ])
    assert bibgen.render_bib(project) == EXPECTED
    assert bibgen.render_bib(project) == bibgen.render_bib(project)


def test_render_bib_excludes_draft_rejected_entryless():
    project = build_project(notes=[
        _note("a2020", entry={"title": "A", "year": 2020}),
        _note("b2020", status="draft", entry={"title": "B", "year": 2020}),
        _note("c2020", status="rejected", entry={"title": "C", "year": 2020}),
        _note("d2020"),
    ])
    text = bibgen.render_bib(project)
    assert "a2020" in text
    for key in ("b2020", "c2020", "d2020"):
        assert key not in text


def test_render_entry_skips_empty_fields():
    project = build_project(notes=[
        _note("a2020", entry={"title": "A", "year": 2020, "doi": "", "author": []}),
    ])
    text = bibgen.render_bib(project)
    assert "doi" not in text and "author" not in text


def _project_with_bib_file(tmp_path, notes, bib_text=""):
    project = build_project(root=tmp_path, notes=notes)
    project.bib_files = ["references.bib"]
    (tmp_path / "references.bib").write_text(bib_text, encoding="utf-8")
    return project


def test_sync_bib_stats_and_write(tmp_path):
    project = _project_with_bib_file(
        tmp_path, [_note("a2020", entry={"title": "A", "year": 2020})],
        bib_text="@article{old1999,\n  title = {O},\n  year = {1999},\n}\n")
    target, stats = bibgen.sync_bib(project)
    assert target.name == "references.bib"
    assert stats == {"added": 1, "removed": 1, "total": 1}
    content = target.read_text(encoding="utf-8")
    assert content == bibgen.render_bib(project)
    assert "\r\n" not in content and content.startswith("%")


def test_sync_bib_idempotent(tmp_path):
    project = _project_with_bib_file(
        tmp_path, [_note("a2020", entry={"title": "A", "year": 2020})])
    _, first = bibgen.sync_bib(project)
    before = (tmp_path / "references.bib").read_text(encoding="utf-8")
    _, second = bibgen.sync_bib(project)
    assert second == {"added": 0, "removed": 0, "total": 1}
    assert (tmp_path / "references.bib").read_text(encoding="utf-8") == before


def test_sync_bib_brace_error_writes_nothing(tmp_path):
    project = _project_with_bib_file(
        tmp_path, [_note("a2020", entry={"title": "{T", "year": 2020})],
        bib_text="@article{old1999,\n  title = {O},\n  year = {1999},\n}\n")
    with pytest.raises(bibgen.BibValueError):
        bibgen.sync_bib(project)
    assert "old1999" in (tmp_path / "references.bib").read_text(encoding="utf-8")


def test_draft_key_suffixes():
    used = {"smith2020"}
    assert bibgen.draft_key("smith2020", used) == "smith2020a"
    assert bibgen.draft_key("smith2020", used) == "smith2020b"
    assert bibgen.draft_key("fresh2020", used) == "fresh2020"


def test_key_base_from_entry():
    from weft.models.bib import BibEntryFields
    assert bibgen.key_base_from_entry(BibEntryFields.model_validate(
        {"title": "Ignored", "author": ["Smith, Jane"], "year": 2020})) == "smith2020"
    assert bibgen.key_base_from_entry(BibEntryFields.model_validate(
        {"title": "Thermally activated", "year": 2020})) == "thermally2020"


def test_render_entry_zero_fields_raises(tmp_path):
    project = build_project(notes=[
        _note("a2020", entry={"title": "", "year": ""}),
    ])
    with pytest.raises(bibgen.BibValueError):
        bibgen.render_bib(project)
    project.bib_files = ["references.bib"]
    (tmp_path / "references.bib").write_text(
        "@article{old1999,\n  title = {O},\n  year = {1999},\n}\n", encoding="utf-8")
    with pytest.raises(bibgen.BibValueError):
        bibgen.sync_bib(project)
    assert "old1999" in (tmp_path / "references.bib").read_text(encoding="utf-8")


def test_render_entry_fields_overlap_raises():
    project = build_project(notes=[
        _note("a2020", entry={"title": "T", "year": 2020, "fields": {"title": "dup"}}),
    ])
    with pytest.raises(bibgen.BibValueError):
        bibgen.render_bib(project)


def test_render_entry_multi_fields_sorted():
    project = build_project(notes=[
        _note("a2020", entry={"title": "T", "year": 2020,
                              "fields": {"zeta": "1", "alpha": "2"}}),
    ])
    lines = bibgen.render_bib(project).splitlines()
    alpha_i = next(i for i, ln in enumerate(lines) if ln.startswith("  alpha = "))
    zeta_i = next(i for i, ln in enumerate(lines) if ln.startswith("  zeta = "))
    assert alpha_i < zeta_i


def test_key_base_whitespace_title():
    from weft.models.bib import BibEntryFields
    assert bibgen.key_base_from_entry(BibEntryFields.model_validate(
        {"title": "  ", "year": 2020})) == "ref2020"


def test_sync_tmp_cleaned_on_failure(tmp_path, monkeypatch):
    project = _project_with_bib_file(
        tmp_path, [_note("a2020", entry={"title": "A", "year": 2020})])

    def _boom(src, dst):
        raise OSError("目标被占用")

    monkeypatch.setattr(bibgen.os, "replace", _boom)
    with pytest.raises(OSError):
        bibgen.sync_bib(project)
    assert not (tmp_path / "references.bib.tmp").exists()

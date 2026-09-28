"""managed 模式校验：E-BIB-SHAPE / W-BIB-ETYPE / W-BIB-STALE / E-NOTE-NOT-IN-BIB 语义。"""
from weft import bibgen
from weft.store.loader import load_project
from tests.helpers import make_managed_project, make_minimal_project, write_card, write_yaml
from weft.validation import validate_project


def _managed_fresh(root):
    make_managed_project(root)
    project, _ = load_project(root)
    (root / "references.bib").write_text(bibgen.render_bib(project), encoding="utf-8")
    project, _ = load_project(root)
    return project


def test_managed_fresh_no_bib_diagnostics(tmp_path):
    project = _managed_fresh(tmp_path)
    codes = {d.code for d in validate_project(project)}
    assert not codes & {"E-BIB-SHAPE", "W-BIB-STALE", "W-BIB-ETYPE"}


def test_managed_two_bib_files_shape_error(tmp_path):
    project = _managed_fresh(tmp_path)
    (tmp_path / "manual.bib").write_text("@article{x1,\n title = {X},\n year = {1},\n}\n",
                                         encoding="utf-8")
    write_yaml(tmp_path / "_quarto.yml",
               {"project": {"type": "default"},
                "bibliography": ["references.bib", "manual.bib"]})
    project, _ = load_project(tmp_path)
    assert any(d.code == "E-BIB-SHAPE" for d in validate_project(project))


def test_bib_cfg_error_shape(tmp_path):
    make_managed_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"bib": {"wat": 1}})
    project, _ = load_project(tmp_path)
    assert any(d.code == "E-BIB-SHAPE" and d.path == "weft.yaml"
               for d in validate_project(project))


def test_etype_warning(tmp_path):
    project = _managed_fresh(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "approved",
                "entry": {"type": "blog", "title": "T", "year": 2020}})
    project, _ = load_project(tmp_path)
    assert any(d.code == "W-BIB-ETYPE" for d in validate_project(project))


def test_etype_rejected_skipped(tmp_path):
    project = _managed_fresh(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "rejected",
                "entry": {"type": "blog", "title": "T", "year": 2020}})
    project, _ = load_project(tmp_path)
    assert not any(d.code == "W-BIB-ETYPE" for d in validate_project(project))


def test_stale_warning(tmp_path):
    project = _managed_fresh(tmp_path)
    with open(tmp_path / "references.bib", "a", encoding="utf-8") as f:
        f.write("% 手改痕迹\n")
    assert any(d.code == "W-BIB-STALE" for d in validate_project(project))


def test_approved_note_without_entry_error(tmp_path):
    make_managed_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "approved"})
    project, _ = load_project(tmp_path)
    # 先按当前卡渲染（无 entry → bib 里没有 key2020），再校验
    (tmp_path / "references.bib").write_text(bibgen.render_bib(project), encoding="utf-8")
    project, _ = load_project(tmp_path)
    diags = [d for d in validate_project(project) if d.code == "E-NOTE-NOT-IN-BIB"]
    assert len(diags) == 1 and "entry" in diags[0].message


def test_draft_note_exempt_in_managed(tmp_path):
    project = _managed_fresh(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "new2021",
               {"id": "new2021", "summary": "s", "status": "draft"})
    project, _ = load_project(tmp_path)
    assert not any(d.code == "E-NOTE-NOT-IN-BIB" for d in validate_project(project))


def test_unmanaged_draft_note_still_checked(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "new2021",
               {"id": "new2021", "summary": "s", "status": "draft"})
    project, _ = load_project(tmp_path)
    assert any(d.code == "E-NOTE-NOT-IN-BIB" and d.path.endswith("new2021.md")
               for d in validate_project(project))

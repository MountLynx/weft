"""weft init 骨架生成（M4：scaffold 纯函数）。"""
from pathlib import Path

import pytest

from weft.scaffold import InitCollisionError, init_project
from weft.store.loader import load_project
from weft.validation import validate_project

SCAFFOLD_FILES = (
    "_quarto.yml",
    "overview.md",
    "weft.yaml",
    "index.qmd",
    "assets/references.bib",
    "metadata/figures.yaml",
    "narrative/01-introduction/part-01.md",
)

SCAFFOLD_DIRS = (
    "assets",
    "figures",
    "inspirations",
    "metadata",
    "metadata/data",
    "metadata/facts",
    "metadata/notes",
    "metadata/methods",
    "metadata/params",
    "metadata/claims/cited",
    "metadata/claims/uncited",
    "narrative/01-introduction",
)


def test_init_new_dir_creates_files(tmp_path):
    root = tmp_path / "demo"
    created = init_project(root)
    for rel in SCAFFOLD_FILES:
        assert (root / rel).is_file(), rel
    for path in created:
        assert path.is_file()
    assert (root / "_quarto.yml").read_text(encoding="utf-8").count(
        "bibliography: assets/references.bib") == 1
    assert (root / "narrative" / "01-introduction" / "part-01.md").read_text(
        encoding="utf-8").count("id: sec-01") == 1


def test_init_new_dir_creates_directories(tmp_path):
    root = tmp_path / "demo"
    init_project(root)
    for rel in SCAFFOLD_DIRS:
        assert (root / rel).is_dir(), rel


def test_init_skeleton_validates_clean(tmp_path):
    root = tmp_path / "demo"
    init_project(root)
    project, load_diags = load_project(root)
    diagnostics = load_diags + validate_project(project)
    assert diagnostics == []


def test_init_rejects_nonempty_dir(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    (root / "user-file.txt").write_text("已有内容", encoding="utf-8")
    with pytest.raises(InitCollisionError):
        init_project(root)
    assert [p.name for p in root.iterdir()] == ["user-file.txt"]


def test_init_rejects_file_target(tmp_path):
    target = tmp_path / "occupied"
    target.write_text("这是个文件", encoding="utf-8")
    with pytest.raises(InitCollisionError):
        init_project(target)


def test_init_accepts_empty_existing_dir(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    init_project(root)
    assert (root / "_quarto.yml").is_file()


def test_init_writes_lf_only(tmp_path):
    root = tmp_path / "demo"
    init_project(root)
    for rel in ("_quarto.yml", "weft.yaml", "narrative/01-introduction/part-01.md"):
        assert b"\r" not in (root / rel).read_bytes(), rel

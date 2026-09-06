"""项目扫描：识别、忽略非项目、损坏项目不阻断。"""
from pathlib import Path

from tests.helpers import make_minimal_project, write_card
from weft.web.discovery import scan_projects


def test_scan_lists_weft_project(tmp_path: Path):
    make_minimal_project(tmp_path / "demo")
    entries = scan_projects(tmp_path)
    assert [e.pid for e in entries] == ["demo"]
    entry = entries[0]
    assert entry.available and entry.project is not None
    assert entry.n_cards == 4 and entry.n_errors == 0


def test_scan_ignores_plain_dir(tmp_path: Path):
    make_minimal_project(tmp_path / "demo")
    (tmp_path / "empty").mkdir()
    assert [e.pid for e in scan_projects(tmp_path)] == ["demo"]


def test_broken_project_marked_unavailable(tmp_path: Path):
    make_minimal_project(tmp_path / "demo")
    write_card(tmp_path / "demo" / "metadata" / "data", "oops",
               {"id": "data-01", "status": "draft"})   # 文件名≠id → 加载错误
    entries = scan_projects(tmp_path)
    assert entries[0].available is False and entries[0].project is None
    assert any(d.is_error for d in entries[0].diagnostics)

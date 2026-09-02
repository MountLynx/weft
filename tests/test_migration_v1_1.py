"""v1→v1.1 narrative 迁移脚本：树结构、id 保留、order 删除、LF、幂等。"""
from pathlib import Path

import frontmatter
import pytest

from weft.migrations.v1_1 import migrate_narrative_tree

_V1_FILE = """---
id: sec-03
section: Results
order: 3
nodes:
  - id: para-03-01
    purpose: describe
    uses:
      - {id: fact-01, role: evidence}
    status: approved
---

审阅备注：本节留待补充。
"""


def _v1_project(tmp_path: Path) -> Path:
    (tmp_path / "narrative").mkdir(parents=True)
    (tmp_path / "narrative" / "03-results.md").write_text(_V1_FILE, encoding="utf-8")
    return tmp_path


def test_migration_moves_flat_file_into_chapter_dir(tmp_path):
    work = _v1_project(tmp_path)
    migrated = migrate_narrative_tree(work)
    assert [p.relative_to(work).as_posix() for p in migrated] == \
        ["narrative/03-results/part-01.md"]
    assert not (work / "narrative" / "03-results.md").exists()


def test_migration_preserves_ids_and_drops_order(tmp_path):
    work = _v1_project(tmp_path)
    migrate_narrative_tree(work)
    post = frontmatter.load(work / "narrative" / "03-results" / "part-01.md")
    assert post.metadata["id"] == "sec-03"
    assert post.metadata["section"] == "Results"
    assert "order" not in post.metadata
    assert [n["id"] for n in post.metadata["nodes"]] == ["para-03-01"]
    assert post.metadata["nodes"][0]["uses"] == [{"id": "fact-01", "role": "evidence"}]


def test_migration_preserves_body_and_lf(tmp_path):
    work = _v1_project(tmp_path)
    migrate_narrative_tree(work)
    raw = (work / "narrative" / "03-results" / "part-01.md").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert "审阅备注" in raw.decode("utf-8")


def test_migration_is_idempotent(tmp_path):
    work = _v1_project(tmp_path)
    migrate_narrative_tree(work)
    assert migrate_narrative_tree(work) == []


def test_migration_no_narrative_dir_is_noop(tmp_path):
    assert migrate_narrative_tree(tmp_path) == []


def test_migration_conflicting_target_raises(tmp_path):
    work = _v1_project(tmp_path)
    edited_dir = work / "narrative" / "03-results"
    edited_dir.mkdir()
    edited_text = "---\nid: sec-03\n---\n\n人工编辑版。\n"
    (edited_dir / "part-01.md").write_text(edited_text, encoding="utf-8")
    with pytest.raises(FileExistsError):
        migrate_narrative_tree(work)
    assert (work / "narrative" / "03-results.md").exists()
    assert (edited_dir / "part-01.md").read_text(encoding="utf-8") == edited_text

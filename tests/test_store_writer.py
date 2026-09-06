"""store 写回：save_card / create_card / next_card_id / save_part（webui 设计 §4.2）。"""
from pathlib import Path

import pytest

from tests.helpers import make_minimal_project
from weft.models.cards import DataCard
from weft.store.loader import load_project
from weft.store.writer import create_card, next_card_id, save_card, save_part


def _load(tmp_path: Path):
    project, diags = load_project(make_minimal_project(tmp_path))
    assert not any(d.is_error for d in diags)
    return project


def test_save_card_round_trip(tmp_path: Path):
    project = _load(tmp_path)
    fact = project.facts["fact-01"]
    saved = save_card(project.root, fact.model_copy(update={"comment": "看过，没问题"}))
    assert saved == project.root / "metadata" / "facts" / "fact-01.md"
    project2, diags = load_project(project.root)
    assert not any(d.is_error for d in diags)
    assert project2.facts["fact-01"].comment == "看过，没问题"


def test_save_card_normalizes_crlf_and_lf(tmp_path: Path):
    project = _load(tmp_path)
    card = project.facts["fact-01"].model_copy(update={"comment": "a\r\nb"})
    path = save_card(project.root, card)
    raw = path.read_bytes()
    assert b"\r" not in raw


def test_claim_type_change_moves_file(tmp_path: Path):
    project = _load(tmp_path)
    old_rel = project.card_paths["claim-01"].as_posix()
    claim = project.claims["claim-01"].model_copy(
        update={"claim_type": "cited", "cites": ["key2020"]})
    new_path = save_card(project.root, claim, old_rel=old_rel)
    assert new_path == project.root / "metadata" / "claims" / "cited" / "claim-01.md"
    assert not (project.root / old_rel).exists()
    project2, diags = load_project(project.root)
    assert not any(d.is_error for d in diags)
    assert "claim-01" in project2.claims


def test_create_card_rejects_duplicate(tmp_path: Path):
    project = _load(tmp_path)
    dup = DataCard(id="data-01", status="draft")
    with pytest.raises(FileExistsError):
        create_card(project.root, dup)


def test_next_card_id_skips_used_and_carries(tmp_path: Path):
    project = _load(tmp_path)
    assert next_card_id(project, "data") == "data-02"
    (project.root / "metadata" / "data" / "data-02.md").write_text(
        "---\nid: data-02\nstatus: draft\n---\n", encoding="utf-8")
    (project.root / "metadata" / "data" / "data-03.md").write_text(
        "---\nid: data-03\nstatus: draft\n---\n", encoding="utf-8")
    project2, diags = load_project(project.root)
    assert not any(d.is_error for d in diags)
    assert next_card_id(project2, "data") == "data-04"
    for n in range(4, 10):   # data-04..data-09 全占 → 进位到 data-10
        (project.root / "metadata" / "data" / f"data-{n:02d}.md").write_text(
            f"---\nid: data-{n:02d}\nstatus: draft\n---\n", encoding="utf-8")
    project3, _ = load_project(project.root)
    assert next_card_id(project3, "data") == "data-10"


def test_save_part_round_trip(tmp_path: Path):
    project = _load(tmp_path)
    part_path = project.root / project.part_paths["sec-01"]
    import frontmatter
    post = frontmatter.load(part_path)
    # python-frontmatter 1.3.0：正文是 .content（.body 赋值是静默 no-op）
    post.content = "审阅备注：正文区不放终稿。"
    part_path.write_text(frontmatter.dumps(post), encoding="utf-8")

    project, _ = load_project(project.root)
    part = project.parts[0]
    part.nodes[0].comment = "改过 comment"
    saved = save_part(project, part)
    assert saved == part_path
    project2, diags = load_project(project.root)
    assert not any(d.is_error for d in diags)
    part2 = next(p for p in project2.parts if p.id == "sec-01")
    assert part2.nodes[0].comment == "改过 comment"
    assert "审阅备注" in part_path.read_text(encoding="utf-8")

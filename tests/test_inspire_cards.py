"""inspire 受控写入器（红线 4 扩展）：草稿卡 → metadata/，提案 → inspirations/proposals/。"""
import pytest

from weft.engine.inspire.cards import write_proposal, write_proposed_cards
from weft.store.project import Project
from pathlib import Path

FACT_FIELDS = {"id": "fact-09", "status": "draft", "data": ["data-01"],
               "statement": "温度提高速率。", "supports": [], "comment": ""}
CLAIM_FIELDS = {"id": "claim-09", "status": "draft", "claim_type": "cited",
                "statement": "温度有正效应。", "cites": [], "comment": ""}


def _project(tmp_path: Path) -> Project:
    return Project(root=tmp_path)


def test_write_fact_card_to_metadata(tmp_path):
    paths = write_proposed_cards(_project(tmp_path),
                                 [("fact", dict(FACT_FIELDS))])
    path = tmp_path / "metadata" / "facts" / "fact-09.md"
    assert paths == [path] and path.is_file()
    assert "id: fact-09" in path.read_text(encoding="utf-8")


def test_write_claim_card_follows_claim_type_subdir(tmp_path):
    write_proposed_cards(_project(tmp_path), [("claim", dict(CLAIM_FIELDS))])
    assert (tmp_path / "metadata" / "claims" / "cited" / "claim-09.md").is_file()
    uncited = dict(CLAIM_FIELDS, id="claim-10", claim_type="uncited")
    write_proposed_cards(_project(tmp_path), [("claim", uncited)])
    assert (tmp_path / "metadata" / "claims" / "uncited" / "claim-10.md").is_file()


def test_write_normalizes_crlf(tmp_path):
    fields = dict(FACT_FIELDS, statement="第一行\r\n第二行")
    write_proposed_cards(_project(tmp_path), [("fact", fields)])
    text = (tmp_path / "metadata" / "facts" / "fact-09.md").read_bytes()
    assert b"\r" not in text


def test_write_proposal_path_and_rejects_escape(tmp_path):
    proposal_fields = dict(FACT_FIELDS, id="fact-01")
    path = write_proposal(_project(tmp_path), "fact-01", proposal_fields)
    assert path == tmp_path / "inspirations" / "proposals" / "fact-01.md"
    assert path.is_file()
    with pytest.raises(ValueError):
        write_proposal(_project(tmp_path), "../evil", dict(proposal_fields))
    with pytest.raises(ValueError):
        write_proposal(_project(tmp_path), "fact-01", dict(FACT_FIELDS))

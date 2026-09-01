import pytest
from pydantic import ValidationError

from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard


def test_data_card_full():
    card = DataCard.model_validate({
        "id": "data-01",
        "refs": ["fig-01a"],
        "source": "../../data/raw/run3.csv",
        "description": "60°C与25°C下三组重复的反应速率测量",
        "status": "draft",
        "comment": "",
    })
    assert card.refs == ["fig-01a"]
    assert card.source == "../../data/raw/run3.csv"


def test_data_card_defaults():
    card = DataCard(id="data-01", status="approved")
    assert card.refs == []
    assert card.source is None
    assert card.description == ""
    assert card.comment == ""


def test_fact_card_spec_example():
    fact = FactCard.model_validate({
        "id": "fact-01",
        "data": ["data-01", "data-02"],
        "statement": "在60 °C时反应速率比25 °C提高42%（p < 0.01）。",
        "supports": ["claim-01"],
        "status": "approved",
    })
    assert fact.data == ["data-01", "data-02"]


def test_fact_data_empty_is_invalid():
    with pytest.raises(ValidationError):
        FactCard(id="fact-01", data=[], statement="s", status="draft")


def test_claim_type_limited_to_two_values():
    with pytest.raises(ValidationError):
        ClaimCard(id="claim-01", claim_type="hypothesis", statement="s", status="draft")


def test_claim_cites_default_empty():
    claim = ClaimCard(id="claim-01", claim_type="cited", statement="s", status="draft")
    assert claim.cites == []


def test_status_vocabulary_enforced():
    with pytest.raises(ValidationError):
        DataCard(id="data-01", status="pending")


def test_unknown_frontmatter_key_rejected():
    # 拼错字段名（ref 而非 refs）必须在解析期报错
    with pytest.raises(ValidationError):
        DataCard.model_validate({"id": "data-01", "status": "draft", "ref": ["fig-01a"]})


def test_note_card_defaults():
    note = NoteCard(id="smith2020", status="draft")
    assert note.summary == ""
    assert note.pdf is None

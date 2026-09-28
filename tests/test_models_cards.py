import pytest
from pydantic import ValidationError

from weft.models.bib import BIB_TYPES
from weft.models.cards import (
    ClaimCard,
    DataCard,
    FactCard,
    MethodCard,
    NoteCard,
    ParamCard,
)


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


def test_method_card_spec_example():
    card = MethodCard.model_validate({
        "id": "qpcr",
        "derived_from": ["tang2025"],
        "statement": "qPCR 定量功能微生物丰度",
        "protocol": "1. 提取 DNA\n2. 体系配置与扩增",
        "status": "approved",
        "comment": "",
    })
    assert card.derived_from == ["tang2025"]
    assert card.protocol.startswith("1. 提取")


def test_method_card_defaults():
    card = MethodCard(id="qpcr", statement="s", protocol="p", status="draft")
    assert card.derived_from == []


def test_param_card_spec_example():
    card = ParamCard.model_validate({
        "id": "qpcr-main",
        "method": "qpcr",
        "values": {"program": "95℃ 3 min", "instrument": "QuantStudio 5"},
        "derived_from": ["trebuch2023"],
        "status": "approved",
    })
    assert card.values["instrument"] == "QuantStudio 5"


def test_param_card_requires_method():
    with pytest.raises(ValidationError):
        ParamCard(id="qpcr-main", values={}, status="draft")


def test_param_card_unknown_key_rejected():
    # 拼写字段名（value 而非 values）必须在解析期报错（extra=forbid）
    with pytest.raises(ValidationError):
        ParamCard.model_validate({"id": "p", "method": "m", "value": {"a": "b"},
                                  "status": "draft"})


def test_note_card_without_entry_loads():
    """向后兼容：旧 note 卡不含 entry 照常加载（红线 2 加法演进）。"""
    card = NoteCard.model_validate({"id": "k1", "status": "approved"})
    assert card.entry is None


def test_note_card_entry_roundtrip():
    card = NoteCard.model_validate({
        "id": "k1", "status": "approved",
        "entry": {"type": "article", "title": "T",
                  "author": ["Smith, Jane", "Lee, Kyung"],
                  "year": 2020, "journal": "J", "volume": "12"},
    })
    assert card.entry.title == "T"
    assert card.entry.year == 2020
    assert card.entry.author == ["Smith, Jane", "Lee, Kyung"]
    # str year 双收：保住 "c. 1850" / "in press" 这类合法值不被收紧成纯 int
    card2 = NoteCard.model_validate({
        "id": "k1", "status": "approved",
        "entry": {"title": "T", "year": "2020"}})
    assert card2.entry.year == "2020"


def test_note_card_entry_forbids_unknown_field():
    with pytest.raises(ValidationError):
        NoteCard.model_validate({
            "id": "k1", "status": "approved",
            "entry": {"title": "T", "year": 2020, "wat": 1}})


def test_note_card_entry_requires_title_and_year():
    with pytest.raises(ValidationError):
        NoteCard.model_validate({
            "id": "k1", "status": "approved", "entry": {"title": "T"}})
    with pytest.raises(ValidationError):
        NoteCard.model_validate({
            "id": "k1", "status": "approved", "entry": {"year": 2020}})


def test_bib_types_vocab():
    assert {"article", "book", "inproceedings", "misc"} <= BIB_TYPES

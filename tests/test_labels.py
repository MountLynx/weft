"""labels：key 字段映射、截断、实体摘要、批量标签（语义可见性 T1）。"""
from weft.labels import KIND_ATTRS, KEY_FIELD, cap, entity_digest, find_card, label_map
from weft.models.cards import (
    ClaimCard, DataCard, FactCard, MethodCard, NoteCard, ParamCard,
)
from tests.helpers import build_project


def _project(**overrides):
    base = dict(
        data=[DataCard(id="data-01", status="approved",
                       description="60°C 速率-时间测量值")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="温度提高速率。",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited",
                          statement="温度有正效应。", status="approved")],
        notes=[NoteCard(id="key2020", summary="文献概括。", status="approved")],
        methods=[MethodCard(id="qpcr", statement="qPCR 三步法。", protocol="p",
                            status="approved")],
        params=[ParamCard(id="qpcr-main", method="qpcr", status="approved")],
    )
    base.update(overrides)
    return build_project(**base)


def test_key_field_mapping():
    assert KEY_FIELD == {"data": "description", "fact": "statement",
                         "claim": "statement", "note": "summary",
                         "method": "statement", "param": "method"}


def test_cap_truncates_long_text():
    assert cap("x" * 41) == "x" * 40 + "…"
    assert cap("短文本") == "短文本"


def test_entity_digest_reads_key_field_per_kind():
    project = _project()
    assert entity_digest(project, "data-01") == "60°C 速率-时间测量值"
    assert entity_digest(project, "fact-01") == "温度提高速率。"
    assert entity_digest(project, "claim-01") == "温度有正效应。"
    assert entity_digest(project, "key2020") == "文献概括。"
    assert entity_digest(project, "qpcr") == "qPCR 三步法。"
    assert entity_digest(project, "qpcr-main") == "qpcr"   # param → method 引用 id


def test_entity_digest_empty_and_missing():
    project = _project(data=[DataCard(id="data-02", status="draft")])
    assert entity_digest(project, "data-02") == ""   # key 字段缺省为空
    assert entity_digest(project, "ghost") == ""     # 未命中实体


def test_entity_digest_custom_limit():
    project = _project()
    assert entity_digest(project, "fact-01", limit=3) == "温度提" + "…"


def test_label_map_batch():
    labels = label_map(_project(), ["fact-01", "ghost", "data-01"])
    assert labels == {"fact-01": "温度提高速率。", "ghost": "",
                      "data-01": "60°C 速率-时间测量值"}


def test_find_card_across_kinds_and_unknown():
    project = _project()
    kind, card = find_card(project, "key2020")
    assert kind == "note" and card.summary == "文献概括。"
    assert find_card(project, "ghost") is None


def test_kind_attrs_match_project_tables():
    project = _project()
    for kind, attr in KIND_ATTRS.items():
        assert getattr(project, attr), kind

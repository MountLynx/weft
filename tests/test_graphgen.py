from weft.graphgen.index import build_index, orphan_ids, used_ids
from weft.models.cards import ClaimCard, DataCard, FactCard
from weft.models.narrative import NarrativeSection, Node, Use
from tests.helpers import build_project


def _project(**overrides):
    """一个全连通的小项目：fact-01 被叙事使用，claim-01/data-01 经它可达。"""
    base = dict(
        data=[DataCard(id="data-01", status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        supports=["claim-01"], status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                          status="approved")],
        sections=[NarrativeSection(id="sec-01", section="Results", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )
    base.update(overrides)
    return build_project(**base)


def test_index_reverse_edges():
    index = build_index(_project())
    assert index["version"] == 1
    entities = index["entities"]
    assert entities["data-01"]["kind"] == "data"
    assert entities["data-01"]["status"] == "approved"
    assert entities["data-01"]["referenced_by"]["facts"] == ["fact-01"]
    # data 经 fact 间接可达叙事节点
    assert entities["data-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert entities["claim-01"]["referenced_by"]["facts"] == ["fact-01"]
    # claim 经 fact.supports 间接可达叙事节点
    assert entities["claim-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert entities["fact-01"]["referenced_by"]["nodes"] == ["para-01-01"]


def test_used_ids_and_orphans():
    project = _project()
    assert used_ids(project) == {"data": ["data-01"], "facts": ["fact-01"],
                                 "claims": ["claim-01"]}
    assert orphan_ids(project) == {"data": [], "facts": [], "claims": []}


def test_orphan_excludes_rejected():
    project = _project(data=[DataCard(id="data-02", status="rejected")])
    assert orphan_ids(project)["data"] == []


def test_orphan_detected():
    project = _project(data=[DataCard(id="data-02", status="draft")])
    assert orphan_ids(project)["data"] == ["data-02"]


def test_index_includes_rejected_entities():
    # 反向索引是全量索引，rejected 也收录；筛选取决于消费方
    project = _project(data=[DataCard(id="data-02", status="rejected")])
    assert build_index(project)["entities"]["data-02"]["status"] == "rejected"

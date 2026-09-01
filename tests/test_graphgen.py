from weft.graphgen.index import build_index, orphan_ids, used_ids
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
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


def test_index_tolerates_dangling_refs():
    # 悬空引用是 validation 的职责；build_index 必须静默跳过（Task 10 会在带错项目上调用它）
    project = _project(
        facts=[FactCard(id="fact-01", data=["data-01", "ghost-data"], statement="s",
                        supports=["claim-01", "claim-ghost"], status="approved")],
        sections=[NarrativeSection(id="sec-01", section="R", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence"),
                       Use(id="ghost-use", role="evidence")], status="approved")]),
        ],
        claims=[ClaimCard(id="claim-01", claim_type="cited", statement="s",
                          cites=["ghost-note"], status="approved")],
    )
    index = build_index(project)  # 不得抛异常
    assert "ghost-data" not in index["entities"]
    assert "claim-ghost" not in index["entities"]
    for entry in index["entities"].values():
        for ids in entry["referenced_by"].values():
            assert not any(str(i).startswith("ghost") for i in ids)


def test_direct_claim_seed_reachable():
    # 种子规则：node.uses 直接引用的 claim 也算可达（无需 fact 支撑）
    project = _project(
        facts=[],
        sections=[NarrativeSection(id="sec-01", section="R", order=1, nodes=[
            Node(id="para-01-01", purpose="interpret",
                 uses=[Use(id="claim-01", role="conclusion")], status="approved")]),
        ],
    )
    entities = build_index(project)["entities"]
    assert entities["claim-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert used_ids(project)["claims"] == ["claim-01"]
    assert orphan_ids(project)["claims"] == []


def test_multi_fact_partial_inheritance():
    # fact-A 被用、fact-B 未被用，都 support claim-C → claim-C 只继承 fact-A 的节点
    # fact-02 用悬空 data id 满足 FactCard.data 的 min_length=1（顺带补充悬空跳过覆盖）
    project = _project(
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        supports=["claim-01"], status="approved"),
               FactCard(id="fact-02", data=["ghost-d"], statement="t",
                        supports=["claim-01"], status="approved")],
        sections=[NarrativeSection(id="sec-01", section="R", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )
    entities = build_index(project)["entities"]
    assert entities["claim-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert entities["data-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert used_ids(project)["facts"] == ["fact-01"]  # fact-02 未被叙事使用


def test_note_reverse_edge_and_exclusion():
    project = _project(
        claims=[ClaimCard(id="claim-01", claim_type="cited", statement="s",
                          cites=["smith2020"], status="approved")],
        notes=[NoteCard(id="smith2020", summary="s", status="approved")],
    )
    entities = build_index(project)["entities"]
    assert entities["smith2020"]["referenced_by"]["claims"] == ["claim-01"]
    assert used_ids(project)["claims"] == ["claim-01"]  # note 不进 used/orphan
    # claim-01 经 fact-01.supports 继承叙事节点：可达，故不是孤儿（used/orphan 互为反集）
    assert orphan_ids(project)["claims"] == []
    # note 既不在 used 也不在 orphan：输出无 notes 类别，任何列表都不含 note id
    assert set(used_ids(project)) == {"data", "facts", "claims"}
    assert set(orphan_ids(project)) == {"data", "facts", "claims"}
    assert all("smith2020" not in ids for ids in used_ids(project).values())
    assert all("smith2020" not in ids for ids in orphan_ids(project).values())

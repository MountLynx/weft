from weft.diagnostics import Level
from weft.store.loader import load_project
from tests.helpers import make_minimal_project, write_card


def test_minimal_project_loads_clean(tmp_path):
    make_minimal_project(tmp_path)
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert set(project.data_cards) == {"data-01"}
    assert set(project.facts) == {"fact-01"}
    assert set(project.claims) == {"claim-01"}
    assert set(project.notes) == {"key2020"}
    assert project.card_paths["data-01"].as_posix() == "metadata/data/data-01.md"


def test_filename_mismatch_is_error(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "data", "wrong-name",
               {"id": "data-02", "status": "draft"})
    _, diagnostics = load_project(tmp_path)
    hits = [d for d in diagnostics if d.code == "E-FILENAME-MISMATCH"]
    assert len(hits) == 1
    assert hits[0].path == "metadata/data/wrong-name.md"
    assert hits[0].level is Level.ERROR
    # 卡片仍被装入（不中断加载）
    project, _ = load_project(tmp_path)
    assert "data-02" in project.data_cards


def test_duplicate_id_across_types(tmp_path):
    # note 卡 id 用了实体命名空间的名字 → 全局唯一性检查必须跨类型
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "data-01",
               {"id": "data-01", "status": "draft"})
    _, diagnostics = load_project(tmp_path)
    dup = [d for d in diagnostics if d.code == "E-DUPLICATE-ID"]
    assert len(dup) == 1
    assert "data-01" in dup[0].message


def test_claim_directory_mismatch(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "uncited", "statement": "s",
                "status": "draft"})
    _, diagnostics = load_project(tmp_path)
    hits = [d for d in diagnostics if d.code == "E-CLAIM-DIR-MISMATCH"]
    assert len(hits) == 1
    assert hits[0].field == "claim_type"


def test_broken_frontmatter_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "metadata" / "data" / "data-99.md").write_text(
        "---\nid: data-99\nstatus: bogus\n---\n", encoding="utf-8")
    _, diagnostics = load_project(tmp_path)
    parse = [d for d in diagnostics if d.code == "E-PARSE"]
    assert len(parse) == 1
    assert parse[0].path == "metadata/data/data-99.md"
    assert parse[0].field == "status"


def test_empty_fact_data_is_parse_error(tmp_path):
    # §4「fact.data 为空」由模型层 min_length=1 兜住
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": [], "statement": "s", "status": "draft"})
    _, diagnostics = load_project(tmp_path)
    parse = [d for d in diagnostics if d.code == "E-PARSE"]
    assert len(parse) == 1
    assert parse[0].path == "metadata/facts/fact-02.md"


def test_not_a_project_guard(tmp_path):
    project, diagnostics = load_project(tmp_path)
    assert [d.code for d in diagnostics] == ["E-NOT-A-PROJECT"]
    assert project.data_cards == {}

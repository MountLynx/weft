from weft.store.loader import load_project
from tests.helpers import make_minimal_project, write_card


def test_sections_sorted_by_order(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "02-discussion",
               {"id": "sec-02", "section": "Discussion", "order": 2,
                "nodes": [{"id": "para-02-01", "purpose": "interpret", "uses": [],
                           "status": "approved"}]})
    # order 与文件名顺序相反 + 同 order 用 id 决胜：防止有人用文件名顺序冒充排序
    write_card(tmp_path / "narrative", "00-zzz",
               {"id": "sec-00", "section": "Intro", "order": 0, "nodes": []})
    write_card(tmp_path / "narrative", "05-aaa",
               {"id": "sec-05b", "section": "B", "order": 5, "nodes": []})
    write_card(tmp_path / "narrative", "05-bbb",
               {"id": "sec-05a", "section": "A", "order": 5, "nodes": []})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert [s.id for s in project.sections] == ["sec-00", "sec-01", "sec-02", "sec-05a", "sec-05b"]
    assert project.section_paths["sec-02"].as_posix() == "narrative/02-discussion.md"


def test_duplicate_section_id_first_wins(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "09-dup",
               {"id": "sec-01", "section": "Dup", "order": 9, "nodes": []})
    _, diagnostics = load_project(tmp_path)
    dup = [d for d in diagnostics if d.code == "E-DUPLICATE-ID"]
    assert len(dup) == 1
    project, _ = load_project(tmp_path)
    # first-wins：保留首个 sec-01，后出现的整文件跳过
    assert len([s for s in project.sections if s.id == "sec-01"]) == 1
    assert project.section_paths["sec-01"].as_posix() == "narrative/01-results.md"


def test_section_body_ignored_in_m1(tmp_path):
    # 正文区只放审阅备注（spec §3.5），M1 加载器不解析、不报错
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "02-x",
               {"id": "sec-02", "section": "X", "order": 2, "nodes": []},
               body="审阅备注：本节留待补充。")
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert len(project.sections) == 2


def test_duplicate_node_id_across_sections(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "02-x",
               {"id": "sec-02", "section": "X", "order": 2,
                "nodes": [{"id": "para-01-01", "purpose": "describe", "uses": [],
                           "status": "draft"}]})
    _, diagnostics = load_project(tmp_path)
    hits = [d for d in diagnostics if d.code == "E-DUPLICATE-ID" and "para-01-01" in d.message]
    assert len(hits) == 1


def test_broken_section_frontmatter(tmp_path):
    make_minimal_project(tmp_path)
    # 其余必填字段齐全，只让 order 非法——确保第一个报错就是 order 的 int_parsing
    (tmp_path / "narrative" / "09-bad.md").write_text(
        "---\nid: sec-09\nsection: Bad\norder: not-a-number\n---\n", encoding="utf-8")
    _, diagnostics = load_project(tmp_path)
    parse = [d for d in diagnostics if d.code == "E-PARSE"]
    assert len(parse) == 1
    assert parse[0].path == "narrative/09-bad.md"
    assert parse[0].field == "order"

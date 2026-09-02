from weft.store.loader import load_project
from tests.helpers import make_minimal_project, write_card


def test_parts_sorted_by_directory_path(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative" / "01-introduction" / "02-gap", "part-01",
               {"id": "sec-gap", "section": "Gap", "nodes": []})
    write_card(tmp_path / "narrative" / "01-introduction" / "01-background", "part-01",
               {"id": "sec-bg", "section": "Background", "nodes": []})
    write_card(tmp_path / "narrative" / "00-zzz", "part-01",
               {"id": "sec-00", "section": "Intro", "nodes": []})
    write_card(tmp_path / "narrative" / "03-results" / "part-02", "part-02",
               {"id": "sec-b", "section": "B", "nodes": []})
    write_card(tmp_path / "narrative" / "03-results", "part-01",
               {"id": "sec-a", "section": "A", "nodes": []})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    # 顺序完全由目录路径 + 文件名前缀决定（v1.1 §4.2，order 退役）；
    # sec-01 来自 make_minimal_project（narrative/01-results/part-01.md），按路径插入序位
    assert [p.id for p in project.parts] == [
        "sec-00", "sec-bg", "sec-gap", "sec-01", "sec-a", "sec-b"]
    assert project.part_paths["sec-a"].as_posix() == "narrative/03-results/part-01.md"
    assert project.part_chapters["sec-a"] == "03-results"
    assert project.part_chapters["sec-gap"] == "01-introduction"


def test_duplicate_part_id_first_wins(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative" / "09-dup", "part-01",
               {"id": "sec-01", "section": "Dup", "nodes": []})
    _, diagnostics = load_project(tmp_path)
    dup = [d for d in diagnostics if d.code == "E-DUPLICATE-ID"]
    assert len(dup) == 1
    project, _ = load_project(tmp_path)
    assert len([p for p in project.parts if p.id == "sec-01"]) == 1
    assert project.part_paths["sec-01"].as_posix() == "narrative/01-results/part-01.md"


def test_part_body_ignored(tmp_path):
    # 正文区只放审阅备注（spec §3.5 语义延续），加载器不解析、不报错
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative" / "02-x", "part-01",
               {"id": "sec-02", "section": "X", "nodes": []},
               body="审阅备注：本 part 留待补充。")
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert len(project.parts) == 2


def test_duplicate_node_id_across_parts(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative" / "02-x", "part-01",
               {"id": "sec-02", "section": "X",
                "nodes": [{"id": "para-01-01", "purpose": "describe", "uses": [],
                           "status": "draft"}]})
    _, diagnostics = load_project(tmp_path)
    hits = [d for d in diagnostics
            if d.code == "E-DUPLICATE-ID" and "para-01-01" in d.message]
    assert len(hits) == 1


def test_retired_order_field_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative" / "09-old", "part-01",
               {"id": "sec-09", "section": "Old", "order": 9, "nodes": []})
    _, diagnostics = load_project(tmp_path)
    parse = [d for d in diagnostics if d.code == "E-PARSE"]
    assert len(parse) == 1
    assert parse[0].path == "narrative/09-old/part-01.md"
    assert parse[0].field == "order"


def test_flat_part_without_chapter_is_error(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "09-flat",
               {"id": "sec-flat", "section": "Flat", "nodes": []})
    _, diagnostics = load_project(tmp_path)
    hits = [d for d in diagnostics if d.code == "E-PART-NO-CHAPTER"]
    assert len(hits) == 1
    assert hits[0].path == "narrative/09-flat.md"

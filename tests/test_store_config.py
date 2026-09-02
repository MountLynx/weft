from weft.store.loader import load_project
from tests.helpers import make_minimal_project, write_yaml


def test_figures_dir_override(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"figures_dir": "assets/figs"})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.figures_dir == "assets/figs"


def test_figures_yaml_entries_loaded(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "metadata" / "figures.yaml",
               {"fig-01": {"caption": "总图注", "subfigs": {"a": "子图a", "b": "子图b"}},
                "tbl-01": {"caption": "表格注"}})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.figures["fig-01"].subfigs == {"a": "子图a", "b": "子图b"}
    assert project.figures["tbl-01"].subfigs == {}


def test_bibliography_as_list_with_missing_file(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "_quarto.yml",
               {"bibliography": ["references.bib", "missing.bib"]})
    project, diagnostics = load_project(tmp_path)
    miss = [d for d in diagnostics if d.code == "E-BIB-MISSING"]
    assert len(miss) == 1
    assert "missing.bib" in miss[0].message
    assert project.bib_keys == {"key2020"}  # 存在的 bib 正常解析


def test_bib_keys_ignore_string_entries(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "references.bib").write_text(
        "@string{jan = \"January\",}\n"
        "@article{key2020,\n  title = {T},\n  year = {2020},\n}\n"
        "@inproceedings{doe2021,\n  title = {D},\n  year = {2021},\n}\n",
        encoding="utf-8")
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.bib_keys == {"key2020", "doe2021"}


def test_no_bibliography_field_is_fine(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "_quarto.yml", {"project": {"type": "default"}})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.bib_keys == set()


def test_empty_bibliography_string_is_unset(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "_quarto.yml", {"bibliography": ""})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.bib_keys == set()


def test_bibliography_list_with_non_string_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "_quarto.yml", {"bibliography": [123]})
    project, diagnostics = load_project(tmp_path)
    assert [d.code for d in diagnostics] == ["E-PARSE"]
    assert diagnostics[0].field == "bibliography"


def test_bibliography_scalar_int_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "_quarto.yml", {"bibliography": 123})
    project, diagnostics = load_project(tmp_path)
    assert [d.code for d in diagnostics] == ["E-PARSE"]
    assert diagnostics[0].field == "bibliography"


def test_bib_path_is_directory_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "bibdir").mkdir()
    write_yaml(tmp_path / "_quarto.yml", {"bibliography": "bibdir"})
    project, diagnostics = load_project(tmp_path)
    assert [d.code for d in diagnostics] == ["E-PARSE"]
    assert project.bib_keys == set()


def test_quarto_yml_as_directory_no_crash(tmp_path):
    # _quarto.yml 是目录：读取失败必须转诊断，不得抛异常
    make_minimal_project(tmp_path)
    (tmp_path / "_quarto.yml").unlink()
    (tmp_path / "_quarto.yml").mkdir()
    project, diagnostics = load_project(tmp_path)
    assert "E-PARSE" in [d.code for d in diagnostics]


def test_figures_yaml_non_utf8_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "metadata" / "figures.yaml").write_bytes(b"fig-01: \xb0\xc2\n")
    project, diagnostics = load_project(tmp_path)
    assert [d.code for d in diagnostics] == ["E-PARSE"]


def test_assemble_mode_defaults_strict(tmp_path):
    make_minimal_project(tmp_path)
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.assemble_mode == "strict"


def test_assemble_mode_lenient_loaded(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"assemble_mode": "lenient"})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.assemble_mode == "lenient"


def test_assemble_mode_invalid_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"assemble_mode": "bogus"})
    _, diagnostics = load_project(tmp_path)
    parse = [d for d in diagnostics if d.code == "E-PARSE"]
    assert len(parse) == 1
    assert parse[0].field == "assemble_mode"

"""draft v2 tasklist：六节点链、inputs 注入、占位符规则进 prompt。"""
from tests.helpers import make_minimal_project
from weft.store.loader import load_project
from weft.engine.spec_build import build_node_spec, build_tasklist


def _spec(tmp_path):
    project, _ = load_project(make_minimal_project(tmp_path))
    part = project.parts[0]
    node = part.nodes[0]
    return project, part, node, build_node_spec(project, node)


def test_six_tick_chain(tmp_path):
    project, part, node, spec = _spec(tmp_path)
    tl = build_tasklist(project, node, spec, "总述", "core", {})
    assert list(tl.tasks) == ["g", "c1", "l", "p", "c2", "f"]
    assert tl.flow.splitlines() == [
        "[g] --> c1", "c1 --> l", "l --> p", "p --> c2", "c2 --> f"]
    assert tl.tasks["f"].type == "script"
    assert tl.tasks["c1"].inputs == {"g": "g"}
    assert tl.tasks["l"].inputs == {"g": "g", "c1": "c1"}
    assert tl.tasks["p"].inputs == {"l": "l"}
    assert tl.tasks["c2"].inputs == {"p": "p"}
    assert tl.tasks["f"].inputs == {"g": "g", "c1": "c1", "l": "l",
                                    "p": "p", "c2": "c2"}


def test_node_spec_fact_data_carries_figure_captions(tmp_path):
    """设计 §6.1 实体全文含 caption：data 条目带 refs 图注（label+caption+子图说明）。"""
    project, part, node, spec = _spec(tmp_path)
    data_entry = spec["uses"][0]["data"][0]
    assert data_entry["refs"] == [
        {"label": "fig-01a", "caption": "速率曲线", "subfig": "60°C"}]
    p = build_tasklist(project, node, spec, "", "", {}).tasks["g"].prompt
    assert "速率曲线" in p and "60°C" in p


def test_node_spec_ref_caption_degrades_gracefully(tmp_path):
    """悬空 ref 只给 label；整图 ref（无子图后缀）不造 subfig 键。"""
    from tests.helpers import write_card
    root = make_minimal_project(tmp_path)
    write_card(root / "metadata" / "data", "data-02",
               {"id": "data-02", "refs": ["tbl-09", "fig-01"], "status": "approved"})
    write_card(root / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-02"], "statement": "产率不变。",
                "status": "approved"})
    project, _ = load_project(root)
    part = project.parts[0]
    node = part.nodes[0]
    node.uses.append(type(node.uses[0])(id="fact-02", role="evidence"))
    spec = build_node_spec(project, node)
    refs = spec["uses"][1]["data"][0]["refs"]
    assert refs[0] == {"label": "tbl-09"}
    assert refs[1] == {"label": "fig-01", "caption": "速率曲线"}


def test_gen_prompt_carries_overview_uses_and_rules(tmp_path):
    project, part, node, spec = _spec(tmp_path)
    p = build_tasklist(project, node, spec, "研究总述全文", "core 指令", {}) \
        .tasks["g"].prompt
    assert "【draft·起草】" in p and "研究总述全文" in p and "core 指令" in p
    assert "fact-01" in p and "data-01" in p
    assert "{{fact-xx}}" in p and "cited" in p and "uncited" in p


def test_check_link_polish_prompts_inject_views(tmp_path):
    project, part, node, spec = _spec(tmp_path)
    tl = build_tasklist(project, node, spec, "", "", {})
    assert "起草稿审查" in tl.tasks["c1"].prompt and "{g}" in tl.tasks["c1"].prompt
    assert "跨段衔接" in tl.tasks["l"].prompt
    assert "{g}" in tl.tasks["l"].prompt and "{c1}" in tl.tasks["l"].prompt
    assert "<<<PARAGRAPH" in tl.tasks["p"].prompt and "{l}" in tl.tasks["p"].prompt
    assert "润色后复检" in tl.tasks["c2"].prompt and "{p}" in tl.tasks["c2"].prompt


def test_node_spec_drops_unapproved_uses(tmp_path):
    from tests.helpers import write_card
    project, _ = load_project(make_minimal_project(tmp_path))
    write_card(tmp_path / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-01"], "statement": "draft 卡",
                "status": "draft"})
    part = project.parts[0]
    node = part.nodes[0]
    node.uses.append(type(node.uses[0])(id="fact-02", role="evidence"))
    spec = build_node_spec(project, node)
    assert [u["id"] for u in spec["uses"]] == ["fact-01"]

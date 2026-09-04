"""inspire 任务表构造：t01–t04 链式 flow、inputs 注入、JSON 输出格式。"""
from weft.engine.inspire.spec_build import build_inspire_tasklist

TEXT = "随手记：升温好像让反应变快。"
DIGEST = "== fact ==\nfact-01 | approved | ..."

def _tasklist():
    return build_inspire_tasklist(TEXT, DIGEST)


def test_chain_flow_single_edge_per_line():
    tl = _tasklist()
    assert list(tl.tasks) == ["t01", "t02", "t03", "t04"]
    lines = tl.flow.splitlines()
    assert lines == ["[t01] --> t02", "t02 --> t03", "t03 --> t04"]


def test_inputs_inject_predecessor_outputs():
    tl = _tasklist()
    assert not getattr(tl.tasks["t01"], "inputs", None)
    assert not getattr(tl.tasks["t02"], "inputs", None)
    assert tl.tasks["t03"].inputs == {"t02": "t02"}
    assert tl.tasks["t04"].inputs == {"t02": "t02", "t03": "t03"}


def test_prompts_carry_markers_content_and_json_format():
    tl = _tasklist()
    p1, p2 = tl.tasks["t01"].prompt, tl.tasks["t02"].prompt
    p3, p4 = tl.tasks["t03"].prompt, tl.tasks["t04"].prompt
    assert "【灵感·逻辑核查】" in p1 and TEXT in p1
    assert "【灵感·卡片拆解】" in p2 and TEXT in p2
    assert "【灵感·现有卡审查】" in p3 and DIGEST in p3 and "{t02}" in p3
    assert "【灵感·匹配】" in p4 and "{t02}" in p4 and "{t03}" in p4
    for t in tl.tasks.values():
        assert t.type == "harness"
        assert t.outputformat == {"type": "json_object"}

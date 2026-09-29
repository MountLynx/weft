"""chapter → 生成工作流判定（显式字段 → 目录前缀 → results 兜底）。"""
from weft.models.narrative import NarrativePart
from weft.workflow import WORKFLOW_SPECS, WORKFLOW_VOCAB, resolve_workflow


def test_explicit_workflow_wins():
    part = NarrativePart(id="p1", section="T", workflow="methods")
    assert resolve_workflow(part, "03-results-and-discussion") == "methods"


def test_chapter_prefix_match_strips_numeric_prefix():
    part = NarrativePart(id="p1", section="T")
    assert resolve_workflow(part, "01-introduction") == "introduction"
    assert resolve_workflow(part, "02-methods") == "methods"
    assert resolve_workflow(part, "03-results-and-discussion") == "results"
    assert resolve_workflow(part, "04-discussion") == "discussion"


def test_no_match_falls_back_to_results():
    part = NarrativePart(id="p1", section="T")
    assert resolve_workflow(part, "05-appendix") == "results"
    assert resolve_workflow(part, "99-中文目录") == "results"


def test_specs_cover_vocab_with_all_fields():
    for name in WORKFLOW_VOCAB:
        spec = WORKFLOW_SPECS[name]
        assert set(spec) == {"prompt_core", "temperature"}
        assert 0 < spec["temperature"] < 1
        assert "只准使用任务提示中列出的实体" in spec["prompt_core"] or name == "methods"
    # §4.3 温度梯度：methods 低 < results 中 < introduction 中 < discussion 中高
    assert (WORKFLOW_SPECS["methods"]["temperature"]
            < WORKFLOW_SPECS["results"]["temperature"]
            < WORKFLOW_SPECS["introduction"]["temperature"]
            < WORKFLOW_SPECS["discussion"]["temperature"])
    # results prompt/温度回归钉：M2 实测调过的 prompt 与温度是契约，防静默漂移
    results = WORKFLOW_SPECS["results"]
    assert results["prompt_core"].startswith("你是学术写作引擎 weft 的行文器。")
    assert "不得引入任何未给出的数据、观点或结论" in results["prompt_core"]
    assert results["temperature"] == 0.3


def test_prompt_core_has_no_v1_citation_or_output_rules():
    """draft v2 对齐：引用形式（{{claim-xx}}）与输出格式（纯文本）由 gen_prompt
    统一管辖，prompt_core 不得再带 v1 的 [@key] 句尾规则与 JSON 输出指令。"""
    for name in WORKFLOW_VOCAB:
        core = WORKFLOW_SPECS[name]["prompt_core"]
        assert "[@key]" not in core, name
        assert "JSON" not in core, name
    assert "方法章不写文献引注" in WORKFLOW_SPECS["methods"]["prompt_core"]


def test_prompt_core_manuscript_language_is_english():
    """成稿语言钉：四个工作流的 prompt_core 一律指定英文文稿，不得再出现中文成稿。"""
    for name in WORKFLOW_VOCAB:
        core = WORKFLOW_SPECS[name]["prompt_core"]
        assert "（英文，" in core, name
        assert "（中文，" not in core, name

"""LLM 客户端选择：mock（免 key 管线冒烟）与真实（.env / 环境变量）。

设计文档 §6.6 的 MockLLMClient（llm.mock）对 json_object 固定返回
{"result","summary","issues"}，不匹配 draft_para 输出形状（计划决策 4），
故自实现同协议假客户端：complete(**kwargs) → llm.client.LLMResponse。
"""
import json
from pathlib import Path

from llm.client import LLMResponse

from weft.engine.draft_rules import DraftError


class ScriptedLLMClient:
    """按 prompt 关键词分流的假客户端（与 embed_minimal 的 mock 同一模式）：

    - prompt 含"你是对齐检查器"（align_check 内置 prompt_core 标识）→ aligned=true
    - prompt 以【灵感·…】开头（inspire 管线标记）→ 对应节点的默认 JSON
    - 否则视为 draft_para → {"paragraph", "uses", "cites"}
    broken=True 时 draft 通道返回非 JSON（测 E-DRAFT-SHAPE 路径）。
    """

    # inspire 默认响应与 helpers.make_minimal_project 自洽：f1→data-01，c1 uncited。
    _INSPIRE_EXTRACT = json.dumps(
        {"cards": [{"key": "f1", "kind": "fact", "statement": "（mock 事实）搅拌加速溶解。",
                    "placeholder": False, "needs_citation": False},
                   {"key": "c1", "kind": "claim", "statement": "（mock 观点）搅拌是主要因素。",
                    "placeholder": False, "needs_citation": False}],
         "links": [{"from": "f1", "to": "c1"}]}, ensure_ascii=False)
    _INSPIRE_REVIEW = json.dumps(
        {"classifications": [{"key": "f1", "verdict": "new"},
                             {"key": "c1", "verdict": "new"}]}, ensure_ascii=False)
    _INSPIRE_MATCH = json.dumps(
        {"fact_data": [{"key": "f1", "data_ids": ["data-01"]}],
         "claim_cites": [{"key": "c1", "claim_type": "uncited", "cites": [],
                          "reason": "（mock）无需文献"}],
         "placeholders": []}, ensure_ascii=False)

    def __init__(self, paragraph: str = "（mock 段落）正文。",
                 uses: list[str] | None = None, cites: list[str] | None = None,
                 broken: bool = False, aligned: bool = True,
                 logic_issues: list[str] | None = None) -> None:
        self.paragraph = paragraph
        self.uses = list(uses or [])
        self.cites = list(cites or [])
        self.broken = broken
        self.aligned = aligned
        self.logic_issues = list(logic_issues or [])
        self.prompts: list[str] = []   # 测试断言 prompt 注入用

    async def complete(self, **kwargs) -> LLMResponse:
        prompt = kwargs.get("prompt") or ""
        self.prompts.append(prompt)
        if "【灵感·逻辑核查】" in prompt:
            content = json.dumps({"issues": self.logic_issues}, ensure_ascii=False)
        elif "【灵感·卡片拆解】" in prompt:
            content = self._INSPIRE_EXTRACT
        elif "【灵感·现有卡审查】" in prompt:
            content = self._INSPIRE_REVIEW
        elif "【灵感·匹配】" in prompt:
            content = self._INSPIRE_MATCH
        elif "你是对齐检查器" in prompt:
            content = json.dumps(
                {"aligned": self.aligned,
                 "suggestions": "" if self.aligned else "段落偏离已审观点"})
        elif self.broken:
            content = "这不是 JSON"
        else:
            content = json.dumps(
                {"paragraph": self.paragraph, "uses": self.uses, "cites": self.cites},
                ensure_ascii=False)
        return LLMResponse(content=content, usage={}, finish_reason="end_turn")


def make_client(mock: bool, project_root: Path | None = None):
    """mock=True → ScriptedLLMClient；否则真实客户端（失败转 DraftError/E-DRAFT-FAILED）。

    project_root：config.json / .env / rules.txt 的候选根（SpecModule 回退链最高优先），
    None 时由 LLMConfig.from_env 回退到 Path.cwd()。
    """
    if mock:
        return ScriptedLLMClient()
    try:
        from llm import LLMConfig, create_llm_client

        return create_llm_client(LLMConfig.from_env(project_root=project_root))
    except Exception as exc:
        raise DraftError(f"真实 LLM 客户端构造失败（检查 config.json / .env）：{exc}") from exc

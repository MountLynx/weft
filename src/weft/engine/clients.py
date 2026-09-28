"""LLM 客户端选择：mock（免 key 管线冒烟）与真实（.env / 环境变量）。

设计文档 §6.6 的 MockLLMClient（llm.mock）对 json_object 固定返回
{"result","summary","issues"}，不匹配 weft 各管线输出形状（M2 计划决策 4），
故自实现同协议假客户端：complete(**kwargs) → llm.client.LLMResponse。
"""
import json
import re
from pathlib import Path

from llm.client import LLMResponse

from weft.engine.draft_rules import DraftError

_PARA_RE = re.compile(r"<<<PARAGRAPH\n(.*?)\nPARAGRAPH>>>", re.DOTALL)
_ID_RE = re.compile(r'"id":\s*"((?:fact|claim)-[A-Za-z0-9_-]+)"')
_FIX_RE = re.compile(r'\{"verdict": "fix", "paragraph": ("(?:[^"\\]|\\.)*")\}')


class ScriptedLLMClient:
    """按 prompt 关键词分流的假客户端（与 embed_minimal 的 mock 同一模式）：

    - 【draft·起草】：从 prompt 的 uses JSON 提取实体 id → 段落 + 占位符
    - 【draft·校验】：verdict=pass（check_fix=True 时输出 fix+修正段）
    - 【draft·衔接】/【draft·润色】：回显 <<<PARAGRAPH …>>> 内的文本
    - 【灵感·…】：inspire 管线各节点默认响应（与 make_minimal_project 自洽）
    - 【文章·…】：parse 管线各节点默认响应（与 make_minimal_project 自洽，key2020）。
    broken=True 时 draft 通道返回非 JSON（测 E-DRAFT-SHAPE 路径）。
    """

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
    _PARSE_EXTRACT = json.dumps(
        {"summary": "（mock 摘要）本文研究了搅拌对溶解速率的影响。",
         "cards": [{"key": "f1", "kind": "fact", "statement": "（mock 事实）搅拌加速溶解。",
                    "placeholder": False, "needs_citation": False},
                   {"key": "c1", "kind": "claim", "statement": "（mock 观点）搅拌是主要因素。",
                    "placeholder": False, "needs_citation": False}],
         "links": [{"from": "f1", "to": "c1"}]}, ensure_ascii=False)
    _PARSE_REVIEW = json.dumps(
        {"classifications": [{"key": "f1", "verdict": "new"},
                             {"key": "c1", "verdict": "new"}],
         "note": {"verdict": "new", "reason": "", "merged_summary": ""}},
        ensure_ascii=False)
    _PARSE_MATCH = json.dumps(
        {"fact_data": [{"key": "f1", "data_ids": ["data-01"]}],
         "claim_cites": [{"key": "c1", "claim_type": "cited", "cites": ["key2020"],
                          "reason": "（mock）本篇文献"}],
         "placeholders": []}, ensure_ascii=False)

    def __init__(self, paragraph: str = "（mock 段落）正文。",
                 uses: list[str] | None = None, cites: list[str] | None = None,
                 broken: bool = False, aligned: bool = True,
                 logic_issues: list[str] | None = None,
                 check_fix: str | None = None) -> None:
        self.paragraph = paragraph
        self.uses = list(uses or [])
        self.cites = list(cites or [])
        self.broken = broken
        self.aligned = aligned
        self.logic_issues = list(logic_issues or [])
        self.check_fix = check_fix   # 非 None：draft·校验 输出 fix+该文本
        self.prompts: list[str] = []   # 测试断言 prompt 注入用

    async def complete(self, **kwargs) -> LLMResponse:
        prompt = kwargs.get("prompt") or ""
        self.prompts.append(prompt)
        content = self._respond(prompt)
        return LLMResponse(content=content, usage={}, finish_reason="end_turn")

    def _respond(self, prompt: str) -> str:
        if "【draft·起草】" in prompt:
            ids = list(dict.fromkeys(_ID_RE.findall(prompt)))
            return self.paragraph + "".join(f"{{{{{i}}}}}" for i in ids)
        if "【draft·校验】" in prompt:
            if self.broken:
                return "这不是 JSON"
            if self.check_fix is not None:
                return json.dumps({"verdict": "fix", "paragraph": self.check_fix},
                                  ensure_ascii=False)
            return json.dumps({"verdict": "pass"}, ensure_ascii=False)
        if "【draft·衔接】" in prompt:
            m = _FIX_RE.search(prompt)
            if m:
                return json.loads(m.group(1))
            m = _PARA_RE.search(prompt)
            return m.group(1) if m else self.paragraph
        if "【draft·润色】" in prompt:
            m = _PARA_RE.search(prompt)
            return m.group(1) if m else self.paragraph
        if "【灵感·逻辑核查】" in prompt:
            return json.dumps({"issues": self.logic_issues}, ensure_ascii=False)
        if "【灵感·卡片拆解】" in prompt:
            return self._INSPIRE_EXTRACT
        if "【灵感·现有卡审查】" in prompt:
            return self._INSPIRE_REVIEW
        if "【灵感·匹配】" in prompt:
            return self._INSPIRE_MATCH
        if "【灵感·成卡覆盖】" in prompt:
            return json.dumps({"coverage": []}, ensure_ascii=False)
        if "【文章·逻辑核查】" in prompt:
            return json.dumps({"issues": self.logic_issues}, ensure_ascii=False)
        if "【文章·卡片拆解】" in prompt:
            return self._PARSE_EXTRACT
        if "【文章·现有卡审查】" in prompt:
            return self._PARSE_REVIEW
        if "【文章·匹配】" in prompt:
            return self._PARSE_MATCH
        if "【文章·成卡覆盖】" in prompt:
            return json.dumps({"coverage": []}, ensure_ascii=False)
        return json.dumps(
            {"paragraph": self.paragraph, "uses": self.uses, "cites": self.cites},
            ensure_ascii=False)


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

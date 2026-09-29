"""chapter → 生成工作流映射（v1.1 §4.3）。

判定顺序：part 显式 workflow 字段 → 第一级目录名剥数字前缀后对词表前缀匹配
→ results 兜底。显式值不在词表是校验错误（E-WORKFLOW-UNKNOWN，fail-closed，
防止路由因拼写错误静默落到 results 的生成风格）。

本模块不 import module_harness / llm：validation、engine、cli 三方共用词表，
且不违反分层红线（红线 1 只约束 specmodule 包的 import 位置）。
"""
from __future__ import annotations

import re

from weft.models.narrative import NarrativePart

WORKFLOW_VOCAB = ("introduction", "methods", "results", "discussion")

_NUM_PREFIX = re.compile(r"^[\d\s._-]+")

# temperature 按 §4.3：introduction 中 / methods 低 / results 中（M2 原值）/ discussion 中高；
# draft v2 起 draft_gen harness 消费此温度（v1 的 citation_rules 字段已随占位符体系移除）
WORKFLOW_SPECS: dict[str, dict] = {
    "introduction": {
        "prompt_core": (
            "你是学术写作引擎 weft 的行文器。依据任务提示给出的已审阅论断卡（claim）"
            "与节点要求，为论文引言写一段综述性正文（英文，学术论文语体）。\n"
            "硬性约束：\n"
            "1. 只准使用任务提示中列出的实体及其内容；不得引入任何未给出的文献结论。\n"
            "2. 不得改写、编造实体卡的任何字段值；节点 logic 是本段的组织纲，"
            "按其顺序与侧重展开。"
        ),
        "temperature": 0.5,
    },
    "methods": {
        "prompt_core": (
            "你是学术写作引擎 weft 的行文器。依据任务提示给出的 method 卡（操作协议）"
            "与 param 卡（本项目参数），为论文方法章写一段格式化描述"
            "（英文，学术方法论语体）。\n"
            "硬性约束：\n"
            "1. 只准展开任务提示给出的协议步骤与参数值；"
            "不得虚构任何步骤、试剂、仪器或数值。\n"
            "2. 不得改写实体卡的任何字段值；数值与单位必须与 param.values 完全一致。\n"
            "3. 方法章不写文献引注。"
        ),
        "temperature": 0.2,
    },
    "results": {
        "prompt_core": (
            "你是学术写作引擎 weft 的行文器。依据任务提示给出的已审阅实体与节点要求，"
            "写出一节论文中的一段正文（英文，学术论文语体）。\n"
            "硬性约束：\n"
            "1. 只准使用任务提示中列出的实体及其内容；"
            "不得引入任何未给出的数据、观点或结论。\n"
            "2. 不得改写、编造实体卡的任何字段值。"
        ),
        "temperature": 0.3,
    },
    "discussion": {
        "prompt_core": (
            "你是学术写作引擎 weft 的行文器。依据任务提示给出的已审阅实体与节点要求，"
            "写一段讨论章正文（英文，学术论文语体），侧重结果间的对比、解释与归因。\n"
            "硬性约束：\n"
            "1. 只准使用任务提示中列出的实体及其内容；比较对象限于实体给出的文献。\n"
            "2. 不得改写、编造实体卡的任何字段值。"
        ),
        "temperature": 0.6,
    },
}


def resolve_workflow(part: NarrativePart, chapter_dir: str) -> str:
    """显式字段 → 目录名前缀匹配 → results 兜底（§4.3）。"""
    if part.workflow:
        return part.workflow
    name = _NUM_PREFIX.sub("", chapter_dir).lower()
    for workflow in WORKFLOW_VOCAB:
        if name.startswith(workflow):
            return workflow
    return "results"

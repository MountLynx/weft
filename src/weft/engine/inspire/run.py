"""inspire 管线：节点 schema/harness 内容 + 运行编排（inspire 设计 §4）。

运行机械件已提炼为 engine/pipeline.py（parse 设计 D8）；本模块只提供
inspire 的 cores / tick 模型 / tasklist 构造，并组装 InspireResult。
快照落 generated/inspirations/.runs/（weft 受管目录）。
"""
from dataclasses import dataclass

from weft.digest import build_digest
from weft.engine.inspire.schemas import (
    CoverageOutput,
    ExtractOutput,
    LogicOutput,
    MatchOutput,
    ReviewOutput,
)
from weft.engine.inspire.spec_build import build_inspire_tasklist
from weft.engine.pipeline import PipelineSpec, run_pipeline
from weft.store.project import Project

_HARNESS_CORES = {
    "inspire_logic": "你是灵感笔记的逻辑核查器，只输出 JSON。",
    "inspire_extract": "你是学术写作引擎的卡片拆解器，只输出 JSON。",
    "inspire_review": "你是元数据卡审查器，必须对照现有卡索引穷举比对，只输出 JSON。",
    "inspire_match": "你是文献与数据匹配器，只准使用索引中出现的 key，只输出 JSON。",
    "inspire_cover": "你是成卡覆盖审查器，逐要点对账原文与草案卡，宁可多报不可漏报，只输出 JSON。",
}
_TICK_MODELS = {"t01": LogicOutput, "t02": ExtractOutput,
                "t03": ReviewOutput, "t04": MatchOutput, "t05": CoverageOutput}


class InspireError(Exception):
    """message 首段含 [E-INSPIRE-SHAPE] / [E-INSPIRE-FAILED]（风格同 draft）。"""


@dataclass
class InspireResult:
    run_id: str
    logic: LogicOutput
    extract: ExtractOutput
    review: ReviewOutput
    match: MatchOutput
    coverage: CoverageOutput
    module_id: str = ""
    resumed: bool = False


def _spec(project: Project) -> PipelineSpec:
    return PipelineSpec(
        harness_cores=_HARNESS_CORES,
        tick_models=_TICK_MODELS,
        module_prefix="weft-inspire",
        runs_base=lambda root: root / "generated" / "inspirations" / ".runs",
        code_shape="E-INSPIRE-SHAPE",
        code_failed="E-INSPIRE-FAILED",
        error_cls=InspireError,
    )


def run_inspire(project: Project, text: str, *, client,
                source: str = "inspire") -> InspireResult:
    def _tasklist():
        return build_inspire_tasklist(text, build_digest(project))

    run = run_pipeline(_spec(project), project, _tasklist, client, source)
    return InspireResult(run_id=run.run_id, logic=run.outputs["t01"],
                         extract=run.outputs["t02"], review=run.outputs["t03"],
                         match=run.outputs["t04"], coverage=run.outputs["t05"],
                         module_id=run.run_id, resumed=run.resumed)

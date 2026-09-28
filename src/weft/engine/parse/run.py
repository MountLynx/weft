"""parse 管线运行层：P1–P5 一次 SpecModule run（parse 设计 §4、§7）。

运行机械件复用 engine/pipeline.py（D8 提炼件）；本模块只提供 parse 的
cores / tick 模型 / tasklist 构造与 ParseResult 组装。快照落
generated/articles/.runs/（weft 受管目录）。W-ARTICLE-LONG 为超长提醒：
不阻断不分块（长文提醒见设计 §7）。
"""
from dataclasses import dataclass, field

from weft.digest import build_digest
from weft.engine.parse.schemas import (
    ArticleCoverageOutput,
    ArticleExtractOutput,
    ArticleLogicOutput,
    ArticleMatchOutput,
    ArticleReviewOutput,
)
from weft.engine.parse.spec_build import build_parse_tasklist
from weft.engine.pipeline import PipelineSpec, run_pipeline
from weft.store.project import Project

_HARNESS_CORES = {
    "parse_logic": "你是文章的逻辑核查器，只输出 JSON。",
    "parse_extract": "你是学术写作引擎的文章拆解器，只输出 JSON。",
    "parse_review": "你是元数据卡审查器，必须对照现有卡索引穷举比对，只输出 JSON。",
    "parse_match": "你是文献与数据匹配器，只准使用索引中出现的 key，只输出 JSON。",
    "parse_cover": "你是成卡覆盖审查器，逐要点对账原文与草案卡，宁可多报不可漏报，只输出 JSON。",
}
_TICK_MODELS = {"p01": ArticleLogicOutput, "p02": ArticleExtractOutput,
                "p03": ArticleReviewOutput, "p04": ArticleMatchOutput,
                "p05": ArticleCoverageOutput}
LONG_TEXT_CHARS = 60_000   # 超长提醒阈值（常量不配置化，YAGNI）


class ParseError(Exception):
    """message 首段含 [E-ARTICLE-SHAPE] / [E-ARTICLE-FAILED]（风格同 draft/inspire）。"""


@dataclass
class ParseResult:
    run_id: str
    logic: ArticleLogicOutput
    extract: ArticleExtractOutput
    review: ArticleReviewOutput
    match: ArticleMatchOutput
    coverage: ArticleCoverageOutput
    warnings: list[str] = field(default_factory=list)
    resumed: bool = False


def run_parse(project: Project, text: str, *, client, source: str = "article",
              bib_key: str | None = None) -> ParseResult:
    """运行一次 P1–P5 文章解析管线（parse 设计 §4、§7）。source 决定
    run_id（weft-parse-<slug>），不同文章必须传不同 source，否则断点快照会跨文章串跑。
    """
    mode = "literature" if bib_key else "decompose"
    warnings: list[str] = []
    if len(text) > LONG_TEXT_CHARS:
        warnings.append(
            f"W-ARTICLE-LONG 文章超长（{len(text)} 字符 > {LONG_TEXT_CHARS}），"
            "解析质量可能下降")

    def _tasklist():
        return build_parse_tasklist(text, build_digest(project), mode=mode,
                                    bib_key=bib_key)

    spec = PipelineSpec(
        harness_cores=_HARNESS_CORES,
        tick_models=_TICK_MODELS,
        module_prefix="weft-parse",
        runs_base=lambda root: root / "generated" / "articles" / ".runs",
        code_shape="E-ARTICLE-SHAPE",
        code_failed="E-ARTICLE-FAILED",
        error_cls=ParseError,
    )
    run = run_pipeline(spec, project, _tasklist, client, source)
    return ParseResult(run_id=run.run_id, logic=run.outputs["p01"],
                       extract=run.outputs["p02"], review=run.outputs["p03"],
                       match=run.outputs["p04"], coverage=run.outputs["p05"],
                       warnings=warnings, resumed=run.resumed)

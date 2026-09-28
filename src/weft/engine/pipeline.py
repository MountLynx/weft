"""多节点 SpecModule 管线公用运行层（parse 设计 §8，D8 提炼件）。

从 engine/inspire/run.py 提炼：module 构建、断点续跑/回退、firings 扫描、
节点输出 schema 校验、错误映射全部经 PipelineSpec 参数化；harness cores /
输出 schema / tasklist 构造属于各管线（engine/inspire | engine/parse），
本模块不认识任何具体管线。

与 M2 决策 14c 同语义：harness 失败不流向后继，事后扫描 fail-closed
（failed → code_shape，aborted / 缺输出 → code_failed）。persist 断点续跑：
每 tick 快照落 runs_base 下，失败后重跑经 Module.resume() 从断点续跑。
"""
import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Type

from module_harness import (
    EventBus,
    HarnessConfig,
    HarnessRegistry,
    Module,
    OutputFormat,
    Tasklist,
)
from module_harness.infra.query import load_snapshot_summary, run_db_path
from module_harness.infra.status import query_run_status
from pydantic import BaseModel, ValidationError

from weft.store.project import Project

_TEMPERATURE = 0.2
_MAX_TOKENS = {"max_tokens": 32768}   # SpecModule 默认 4096 会被推理模型思考耗尽（e2e 实测）
_MAX_TICKS = 14                        # 5 节点链 + 余量（M2 决策 14d）


@dataclass
class PipelineSpec:
    """一条管线的全部可变件；其余运行机械件在本模块内固化。"""

    harness_cores: dict[str, str]             # harness 名 → core prompt（顺序即注册序）
    tick_models: dict[str, Type[BaseModel]]   # tick → 输出模型（顺序 = 链序）
    module_prefix: str                        # module_id 前缀，如 weft-inspire
    runs_base: Callable[[Path], Path]         # project.root → 快照 base_dir
    code_shape: str                           # 节点输出不合 schema 的诊断码
    code_failed: str                          # 节点 aborted / 缺输出的诊断码
    error_cls: Type[Exception]                # 管线异常类型（CLI/WebUI 按此捕获）


@dataclass
class PipelineRun:
    run_id: str
    outputs: dict[str, BaseModel]
    resumed: bool = False


def _slug(source: str) -> str:
    # slug 用完整文件名（含扩展名）：文章换名即换 module_id（设计 §4），
    # paper.md 与 paper.txt 不共享断点快照，报告名同理不互相覆盖。
    return re.sub(r"[^A-Za-z0-9_-]+", "-", Path(source).name).strip("-")


def register_harnesses(reg, cores: dict[str, str]) -> None:
    """注册管线各 harness：json_object 输出 + 收敛温度 + 抬高输出上限。"""
    for name, core in cores.items():
        reg.harness(name, HarnessConfig(
            prompt_core=core,
            output_format=OutputFormat(type="json_object"),
            notdo=["不要输出 JSON 以外的任何文本"],
            temperature=_TEMPERATURE,
            api_params=dict(_MAX_TOKENS),
        ))


def run_pipeline(spec: PipelineSpec, project: Project, tasklist_builder: Callable[[], Tasklist],
                 client, source: str) -> PipelineRun:
    """跑一条多节点管线；tasklist_builder() 闭包携带全文/digest/mode。"""
    module_id = f"{spec.module_prefix}-{_slug(source) or 'run'}"[:120]
    base_dir = spec.runs_base(Path(project.root))
    prior = load_snapshot_summary(module_id, base_dir=base_dir)

    resumed = False
    resume_tick = 0
    if prior is not None:
        outs = prior.get("outputs") or {}
        # 失败节点的快照 output 是 Failure 描述字符串（非 dict）——不算完成
        complete = all(isinstance(outs.get(t), dict) for t in spec.tick_models)
        status = query_run_status(module_id, base_dir=base_dir)
        if complete:
            # 上一次已全程完成：同源重跑 = 全新运行，清场防陈旧输出混入
            shutil.rmtree(run_db_path(module_id, base_dir=base_dir).parent,
                          ignore_errors=True)
            prior = None
        elif status is not None and status.phase == "running":
            raise spec.error_cls(
                f"[{spec.code_failed}] run {module_id} 正在运行（phase=running），"
                "不接受并发重跑")
        else:
            # 断点续跑：失败节点在 tickflow 里已被消费（出边写 False），
            # resume 不会重试——须回退到最后一个成功节点的 tick 快照。
            leading = 0
            for tick in spec.tick_models:
                if isinstance(outs.get(tick), dict):
                    leading += 1
                else:
                    break
            if leading == 0:
                shutil.rmtree(run_db_path(module_id, base_dir=base_dir).parent,
                              ignore_errors=True)
            else:
                resumed = True
                resume_tick = leading - 1

    bus = EventBus()
    reg = HarnessRegistry(llm_client=client, event_bus=bus)
    register_harnesses(reg, spec.harness_cores)
    module = Module(
        spec={"task_nodes": {tick: tick for tick in spec.tick_models}},
        tasklist=tasklist_builder(),
        llm_client=client,
        event_bus=bus,
        registry=reg,
        module_id=module_id,
        base_dir=base_dir,
        review_harness=None,      # tasklist 代码构造，跳过一致性审核（M2 决策 2）
        keep_records=True,        # firings 落库：断点取回节点输出 + 审计
        persist=True,             # 每 tick 快照（续跑依赖）
        status_file=True,         # 阶段状态（跨进程查询）
        control=False,
        stream_log=False,
    )
    try:
        if resumed:
            firings = asyncio.run(module.resume(rollback_to=resume_tick,
                                                max_ticks=_MAX_TICKS))
        else:
            firings = asyncio.run(module.run(max_ticks=_MAX_TICKS))
    except Exception as exc:
        raise spec.error_cls(
            f"[{spec.code_failed}] SpecModule run 失败：{exc}") from exc

    # 节点输出：以持久化 firings 的最新值为底（续跑时覆盖已完成节点），
    # 本次 firings 里的输出优先（更新）。
    summary = load_snapshot_summary(module_id, base_dir=base_dir)
    outputs: dict[str, dict] = dict((summary or {}).get("outputs") or {})
    for firing in firings:
        if firing.status == "failed":
            raise spec.error_cls(
                f"[{spec.code_shape}] 节点 {firing.node} 输出不可读："
                f"{firing.error or 'harness 失败'}")
        if firing.status == "aborted":
            raise spec.error_cls(
                f"[{spec.code_failed}] 节点 {firing.node} 基础设施失败：{firing.error}")
        if isinstance(firing.output, dict):
            outputs[firing.node] = firing.output
    missing = {t for t in spec.tick_models
               if not isinstance(outputs.get(t), dict)}
    if missing:
        raise spec.error_cls(
            f"[{spec.code_failed}] 节点未完成：{sorted(missing)}")

    parsed: dict[str, BaseModel] = {}
    for tick, model in spec.tick_models.items():
        try:
            parsed[tick] = model.model_validate(outputs[tick])
        except ValidationError as exc:
            raise spec.error_cls(
                f"[{spec.code_shape}] 节点 {tick} 输出不合 schema："
                f"{exc.errors()[0]['msg']}") from exc
    return PipelineRun(run_id=module_id, outputs=parsed, resumed=resumed)

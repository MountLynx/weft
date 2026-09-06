"""卡片编辑表单规格（webui 设计 §4.1）：字段 → 控件映射 + 表单解析。

引用类字段全部下拉/多选，选项来自项目加载结果（从源头杜绝悬空引用）；
词表字段用 datalist 允许超集（模型层放行，校验层提醒）。
"""
from __future__ import annotations

from dataclasses import dataclass

import yaml
from weft.models.cards import (
    ClaimCard,
    DataCard,
    FactCard,
    MethodCard,
    NoteCard,
    ParamCard,
)
from weft.store.project import Project


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    widget: str            # text | textarea | yaml_map | select | multiselect
    choices: str | None = None
    required: bool = False


FIELD_SPECS: dict[str, list[FieldSpec]] = {
    "data": [FieldSpec("refs", "refs（图号）", "multiselect", "figure_refs"),
             FieldSpec("source", "source（路径/URL/说明）", "text"),
             FieldSpec("description", "description", "textarea")],
    "fact": [FieldSpec("data", "data（依赖的 data 卡）", "multiselect", "data_ids", required=True),
             FieldSpec("statement", "statement", "textarea", required=True),
             FieldSpec("supports", "supports（支持的 claim）", "multiselect", "claim_ids")],
    "claim": [FieldSpec("claim_type", "claim_type", "select", "claim_type", required=True),
              FieldSpec("statement", "statement", "textarea", required=True),
              FieldSpec("cites", "cites（bib key）", "multiselect", "bib_keys")],
    "note": [FieldSpec("summary", "summary", "textarea"),
             FieldSpec("pdf", "pdf（文件路径，可选）", "text")],
    "method": [FieldSpec("statement", "statement", "textarea", required=True),
               FieldSpec("protocol", "protocol", "textarea", required=True),
               FieldSpec("derived_from", "derived_from（bib key）", "multiselect", "bib_keys")],
    "param": [FieldSpec("method", "method（method 卡）", "select", "method_ids", required=True),
              FieldSpec("values", "values（YAML 映射）", "yaml_map"),
              FieldSpec("derived_from", "derived_from（bib key）", "multiselect", "bib_keys")],
}

KIND_MODELS = {"data": DataCard, "fact": FactCard, "claim": ClaimCard,
               "note": NoteCard, "method": MethodCard, "param": ParamCard}
KIND_ID_WIDGET = {"data": "auto", "fact": "auto", "claim": "auto",
                  "note": "bibkey", "method": "slug", "param": "slug"}
KIND_PREFIX = {"data": "data", "fact": "fact", "claim": "claim"}


def build_choices(kind: str, project: Project) -> dict[str, list[str]]:
    return {"figure_refs": sorted(project.figures),
            "data_ids": sorted(project.data_cards),
            "claim_ids": sorted(project.claims),
            "bib_keys": sorted(project.bib_keys),
            "method_ids": sorted(project.methods),
            "claim_type": ["uncited", "cited"]}


def form_to_meta(kind: str, form, *, is_new: bool, card_id: str | None
                 ) -> tuple[dict, dict[str, str]]:
    """表单 → 模型 meta 字典；(meta, 字段级错误)。id 一律服务端裁定。"""
    meta: dict = {}
    errors: dict[str, str] = {}
    for spec in FIELD_SPECS[kind]:
        if spec.widget == "multiselect":
            meta[spec.name] = [str(v) for v in form.getlist(spec.name)]
        elif spec.widget == "yaml_map":
            raw = str(form.get(spec.name) or "").strip()
            parsed: dict = {}
            if raw:
                try:
                    loaded = yaml.safe_load(raw)
                except yaml.YAMLError as exc:
                    errors.setdefault(spec.name, f"YAML 解析失败：{exc}")
                    loaded = {}
                if not isinstance(loaded, dict):
                    errors.setdefault(spec.name, "必须是 YAML 映射（键: 值）")
                    loaded = {}
                parsed = loaded
            meta[spec.name] = parsed
        else:
            meta[spec.name] = str(form.get(spec.name) or "").strip()
    meta["status"] = str(form.get("status", "draft")) or "draft"
    meta["comment"] = str(form.get("comment", ""))
    meta["id"] = str(form.get("id") or "").strip() if is_new else (card_id or "")
    return meta, errors


def validation_errors(exc) -> dict[str, str]:
    """pydantic ValidationError → {字段: 首条消息}。"""
    out: dict[str, str] = {}
    for err in exc.errors():
        key = ".".join(str(p) for p in err["loc"]) or "__all__"
        out.setdefault(key, err["msg"])
    return out


def values_for_template(kind: str, card) -> dict:
    """model_dump → 模板渲染值；param.values 字典转 YAML 文本。"""
    values = card.model_dump()
    if kind == "param":
        values["values"] = yaml.safe_dump(values.get("values") or {},
                                          allow_unicode=True, sort_keys=False)
    return values


def form_to_values(kind: str, form) -> dict:
    """提交表单 → 模板回显值：multiselect 保持列表，其余为字符串（校验失败重渲染用）。"""
    values: dict = {}
    for spec in FIELD_SPECS[kind]:
        if spec.widget == "multiselect":
            values[spec.name] = [str(v) for v in form.getlist(spec.name)]
        else:
            values[spec.name] = str(form.get(spec.name) or "")
    values["status"] = str(form.get("status", "draft"))
    values["comment"] = str(form.get("comment", ""))
    if form.get("id") is not None:
        values["id"] = str(form.get("id"))
    return values

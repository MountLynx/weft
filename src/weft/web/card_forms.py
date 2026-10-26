"""卡片编辑表单规格（webui 设计 §4.1）：字段 → 控件映射 + 表单解析。

引用类字段全部下拉/多选，选项来自项目加载结果（从源头杜绝悬空引用）；
词表字段用 datalist 允许超集（模型层放行，校验层提醒）。
chapters 章节标签用 tags 控件（自由文本 + datalist，card-chapters 设计 §5.1）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import yaml
from weft.labels import cap, label_map
from weft.models.cards import (
    ClaimCard,
    DataCard,
    FactCard,
    MethodCard,
    NoteCard,
    ParamCard,
)
from weft.store.project import Project
from weft.workflow import normalize_chapter

_TAGS_SPLIT = re.compile(r"[,，;；\n]+")


def parse_tags(raw) -> list[str]:
    """tags 控件文本 → 标签列表：逗号/分号/换行分隔，去重保序。"""
    return list(dict.fromkeys(
        p.strip() for p in _TAGS_SPLIT.split(str(raw or "")) if p.strip()))


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    widget: str            # text | textarea | yaml_map | select | multiselect | tags
    choices: str | None = None
    required: bool = False


_CHAPTERS_SPEC = FieldSpec("chapters", "chapters（章节标签）", "tags",
                           "chapter_names")

FIELD_SPECS: dict[str, list[FieldSpec]] = {
    "data": [FieldSpec("refs", "refs（图号）", "multiselect", "figure_refs"),
             FieldSpec("source", "source（路径/URL/说明）", "text"),
             FieldSpec("description", "description", "textarea"),
             _CHAPTERS_SPEC],
    "fact": [FieldSpec("data", "data（依赖的 data 卡）", "multiselect", "data_ids", required=True),
             FieldSpec("statement", "statement", "textarea", required=True),
             FieldSpec("supports", "supports（支持的 claim）", "multiselect", "claim_ids"),
             _CHAPTERS_SPEC],
    "claim": [FieldSpec("claim_type", "claim_type", "select", "claim_type", required=True),
              FieldSpec("statement", "statement", "textarea", required=True),
              FieldSpec("cites", "cites（bib key）", "multiselect", "bib_keys"),
              _CHAPTERS_SPEC],
    "note": [FieldSpec("summary", "summary", "textarea"),
             FieldSpec("pdf", "pdf（文件路径，可选）", "text"),
             FieldSpec("entry", "entry（书目字段，YAML 映射；managed 批准后进 bib）", "yaml_map"),
             _CHAPTERS_SPEC],
    "method": [FieldSpec("statement", "statement", "textarea", required=True),
               FieldSpec("protocol", "protocol", "textarea", required=True),
               FieldSpec("derived_from", "derived_from（bib key）", "multiselect", "bib_keys"),
               _CHAPTERS_SPEC],
    "param": [FieldSpec("method", "method（method 卡）", "select", "method_ids", required=True),
              FieldSpec("values", "values（YAML 映射）", "yaml_map"),
              FieldSpec("derived_from", "derived_from（bib key）", "multiselect", "bib_keys"),
              _CHAPTERS_SPEC],
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
            "claim_type": ["uncited", "cited"],
            # 已知章节归一化名并集（datalist 供参考，允许超集自由输入）
            "chapter_names": sorted({normalize_chapter(c)
                                     for c in project.part_chapters.values()})}


def build_labels(project: Project) -> dict[str, dict[str, str]]:
    """引用控件的标签映射：choices_key → {id: 摘要}（展示附加，提交值不变，设计 D9）。"""
    return {
        "figure_refs": {k: cap(v.caption, 40) for k, v in project.figures.items()},
        "data_ids": label_map(project, sorted(project.data_cards)),
        "claim_ids": label_map(project, sorted(project.claims)),
        "bib_keys": label_map(project, sorted(project.bib_keys)),
        "method_ids": label_map(project, sorted(project.methods)),
        "claim_type": {},
    }


def form_to_meta(kind: str, form, *, is_new: bool, card_id: str | None
                 ) -> tuple[dict, dict[str, str]]:
    """表单 → 模型 meta 字典；(meta, 字段级错误)。id 一律服务端裁定。"""
    meta: dict = {}
    errors: dict[str, str] = {}
    for spec in FIELD_SPECS[kind]:
        if spec.widget == "multiselect":
            meta[spec.name] = [str(v) for v in form.getlist(spec.name)]
        elif spec.widget == "tags":
            meta[spec.name] = parse_tags(form.get(spec.name))
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
    if kind == "note" and not meta.get("entry"):
        meta["entry"] = None   # 空映射 = 无书目字段（避免 BibEntryFields 必填校验误伤，P-D2）
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
    """model_dump → 模板渲染值：None 归一为空串（防字面 "None" 进表单再写回）；
    param.values 字典转 YAML 文本；chapters 列表转逗号分隔文本（tags 控件）。"""
    values = {k: ("" if v is None else v) for k, v in card.model_dump().items()}
    if kind == "param":
        values["values"] = yaml.safe_dump(values.get("values") or {},
                                          allow_unicode=True, sort_keys=False)
    if kind == "note" and values.get("entry"):
        values["entry"] = yaml.safe_dump(values["entry"], allow_unicode=True,
                                         sort_keys=False)
    if isinstance(values.get("chapters"), list):
        values["chapters"] = ", ".join(values["chapters"])
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

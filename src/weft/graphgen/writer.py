"""把索引与可达集写入 generated/：graph.json、used-metadata.json、orphans.md。

JSON 统一 ensure_ascii=False + sort_keys=True + 尾部换行 + LF（newline="\n"，
平台无关），保证输出字节级确定（可黄金比对）。
"""
from __future__ import annotations

import json
from pathlib import Path

from weft.graphgen.index import build_index, orphan_ids, used_ids
from weft.store.project import Project


def write_outputs(project: Project, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = build_index(project)
    used = used_ids(project)
    orphans = orphan_ids(project)

    graph_path = out_dir / "graph.json"
    used_path = out_dir / "used-metadata.json"
    orphans_path = out_dir / "orphans.md"

    graph_path.write_text(_to_json(graph), encoding="utf-8", newline="\n")
    used_path.write_text(_to_json(used), encoding="utf-8", newline="\n")
    orphans_path.write_text(_orphans_md(project, orphans), encoding="utf-8",
                            newline="\n")
    return [graph_path, used_path, orphans_path]


def _to_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _orphans_md(project: Project, orphans: dict[str, list[str]]) -> str:
    lines = ["# 孤儿实体报告", ""]
    total = sum(len(ids) for ids in orphans.values())
    if total == 0:
        lines.append("无孤儿实体。")
        return "\n".join(lines) + "\n"
    lines += ["未被任何叙事节点引用（含间接可达）的实体：", ""]
    titles = {"data": "data", "facts": "fact", "claims": "claim",
              "methods": "method", "params": "param"}
    for group, ids in orphans.items():
        for eid in ids:
            path = project.card_paths.get(eid, Path("?")).as_posix()
            lines.append(f"- {eid}（{titles[group]}）— {path}")
    return "\n".join(lines) + "\n"

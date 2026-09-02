"""v1 → v1.1 narrative 目录树迁移（设计文档 v1.1 §4.2）。

确定性规则：narrative/<stem>.md → narrative/<stem>/part-01.md；
part id 与节点 id 原样保留（决策 2）；order 字段删除（v1.1 退役）；
LF 归一化落盘。幂等：无 v1 扁平文件时不做任何事。
顺序约定：v1.1 的节顺序来自目录/文件名的数字前缀；v1 的 order 字段不映射
（无前缀的 stem 迁移后按字典序定位）。
目标冲突 fail-closed：narrative/<stem>/part-01.md 已存在且内容不同时抛
FileExistsError（内容相同则视为崩溃恢复，原样重写）。

用法：.venv/Scripts/python.exe -m weft.migrations.v1_1 <项目根目录>
前置条件：v1 扁平文件 frontmatter 可正常解析（迁移工具不做容错加载）。
"""
from __future__ import annotations

from pathlib import Path

import frontmatter
import yaml


def migrate_narrative_tree(root: Path) -> list[Path]:
    narrative = root / "narrative"
    if not narrative.is_dir():
        return []
    migrated: list[Path] = []
    for path in sorted(narrative.glob("*.md")):
        post = frontmatter.load(path)
        post.metadata.pop("order", None)
        target_dir = narrative / path.stem
        target_dir.mkdir(parents=True, exist_ok=True)
        text = ("---\n"
                + yaml.safe_dump(post.metadata, allow_unicode=True, sort_keys=False)
                + "---\n"
                + post.content.strip() + "\n")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        target = target_dir / "part-01.md"
        if target.exists() and target.read_text(encoding="utf-8") != text:
            raise FileExistsError(f"迁移目标冲突：{target}")
        target.write_text(text, encoding="utf-8", newline="\n")
        path.unlink()
        migrated.append(target)
    return migrated


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python -m weft.migrations.v1_1 <项目根目录>")
        sys.exit(2)
    root = Path(sys.argv[1])
    for written in migrate_narrative_tree(root):
        print(f"已迁移 {written.relative_to(root).as_posix()}")

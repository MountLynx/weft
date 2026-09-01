import json
from pathlib import Path

from weft.graphgen.index import build_index
from weft.graphgen.writer import write_outputs
from weft.models.cards import DataCard, FactCard
from weft.models.narrative import NarrativeSection, Node, Use
from tests.helpers import build_project


def _project(root=None, data=None):
    """全连通小项目：fact-01 被叙事使用，data-01 经它可达。"""
    return build_project(
        root=root or Path("."),
        data=data or [DataCard(id="data-01", status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s", status="approved")],
        sections=[NarrativeSection(id="sec-01", section="Results", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )


def test_writer_outputs(tmp_path):
    project = _project(root=tmp_path)
    paths = write_outputs(project, tmp_path / "generated")
    assert [p.name for p in paths] == ["graph.json", "used-metadata.json", "orphans.md"]
    graph = json.loads((tmp_path / "generated" / "graph.json").read_text(encoding="utf-8"))
    assert graph == build_index(project)
    used = json.loads(
        (tmp_path / "generated" / "used-metadata.json").read_text(encoding="utf-8"))
    assert used == {"data": ["data-01"], "facts": ["fact-01"], "claims": []}
    orphans = (tmp_path / "generated" / "orphans.md").read_text(encoding="utf-8")
    assert "无孤儿实体" in orphans


def test_orphans_md_lists_paths(tmp_path):
    project = _project(root=tmp_path, data=[
        DataCard(id="data-01", status="approved"),
        DataCard(id="data-02", status="draft"),
    ])
    write_outputs(project, tmp_path / "generated")
    text = (tmp_path / "generated" / "orphans.md").read_text(encoding="utf-8")
    assert "data-02（data）— metadata/data-02.md" in text
    assert "data-01（data）" not in text

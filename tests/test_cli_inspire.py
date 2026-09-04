"""CLI：weft inspire / replace / missing-cites。"""
import os
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def _inspiration(root, name="idea.md", text="随手记：搅拌加速溶解，可能是主因。"):
    path = root / "inspirations" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_cli_inspire_mock_end_to_end(tmp_path):
    make_minimal_project(tmp_path)
    source = _inspiration(tmp_path)
    result = runner.invoke(app, ["inspire", str(source), str(tmp_path), "--mock"])
    assert result.exit_code == 0, result.output
    assert "已写入 metadata/facts/fact-02.md" in result.output
    assert "claims/uncited/claim-02.md" in result.output
    assert (tmp_path / "inspirations" / "processed" / "idea.md").is_file()
    assert not source.exists()
    report = tmp_path / "generated" / "inspirations" / "idea-report.md"
    assert report.is_file() and "报告" in result.output


def test_cli_inspire_rejects_file_outside_inbox(tmp_path):
    make_minimal_project(tmp_path)
    outside = tmp_path / "elsewhere.md"
    outside.write_text("x", encoding="utf-8")
    result = runner.invoke(app, ["inspire", str(outside), str(tmp_path)])
    assert result.exit_code == 1
    assert "inspirations" in result.output


def test_cli_inspire_picks_oldest_without_arg(tmp_path):
    make_minimal_project(tmp_path)
    newer = _inspiration(tmp_path, "new.md")
    older = _inspiration(tmp_path, "old.md")
    os.utime(newer, (2000000000, 2000000000))
    os.utime(older, (1000000000, 1000000000))
    result = runner.invoke(app, ["inspire", str(tmp_path), "--mock"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "inspirations" / "processed" / "old.md").is_file()
    assert newer.is_file()   # 只处理最旧的一个


def test_cli_inspire_empty_inbox_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["inspire", str(tmp_path)])
    assert result.exit_code == 1
    assert "收件箱" in result.output


def test_cli_inspire_validation_gate(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-09",
               {"id": "fact-09", "data": ["data-99"], "statement": "s",
                "status": "draft"})
    source = _inspiration(tmp_path)
    result = runner.invoke(app, ["inspire", str(source), str(tmp_path), "--mock"])
    assert result.exit_code == 1
    assert "拒绝" in result.output
    assert source.exists()   # 闸门拒绝，收件箱不动


def test_cli_inspire_real_client_failure_is_clean(tmp_path):
    """无配置走真实客户端 → 干净 ERROR，不甩 traceback。"""
    make_minimal_project(tmp_path)
    source = _inspiration(tmp_path)
    result = runner.invoke(app, ["inspire", str(source), str(tmp_path)])
    assert result.exit_code == 1
    assert result.output.startswith("ERROR")
    assert "Traceback" not in result.output
    assert source.exists()


def test_cli_missing_cites_lists_and_counts(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "缺文献的观点。",
                "cites": [], "status": "draft"})
    result = runner.invoke(app, ["missing-cites", str(tmp_path)])
    assert result.exit_code == 0
    assert "claim-02" in result.output and "缺文献的观点。" in result.output
    assert result.output.rstrip().endswith("1 张 cited 卡缺文献")
    clean = runner.invoke(app, ["missing-cites", str(tmp_path)])
    assert clean.exit_code == 0


def test_cli_replace_applies_and_archives(tmp_path):
    make_minimal_project(tmp_path)
    proposal = tmp_path / "inspirations" / "proposals" / "fact-01.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text(
        "---\nid: fact-01\nstatus: draft\ndata:\n- data-01\n"
        "statement: 温度提高速率，且随搅拌增强。\nsupports:\n- claim-01\n"
        'comment: "取代 fact-01（灵感补充）"\n---\n', encoding="utf-8")
    result = runner.invoke(app, ["replace", "fact-01", str(tmp_path)])
    assert result.exit_code == 0, result.output
    new_text = (tmp_path / "metadata" / "facts" / "fact-01.md").read_text(encoding="utf-8")
    assert "随搅拌增强" in new_text
    archive = tmp_path / "archive" / "cards" / "facts" / "fact-01.md"
    assert archive.is_file()
    assert "随搅拌增强" not in archive.read_text(encoding="utf-8")  # 旧卡归档
    assert not proposal.exists()


def test_cli_replace_blocked_by_validation_gate(tmp_path):
    make_minimal_project(tmp_path)
    proposal = tmp_path / "inspirations" / "proposals" / "fact-01.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text(
        "---\nid: fact-01\nstatus: draft\ndata:\n- data-99\n"
        "statement: 悬空引用。\nsupports: []\ncomment: \"\"\n---\n", encoding="utf-8")
    result = runner.invoke(app, ["replace", "fact-01", str(tmp_path)])
    assert result.exit_code == 1
    assert (tmp_path / "metadata" / "facts" / "fact-01.md").is_file()
    assert proposal.exists()   # 磁盘零改动


def test_cli_replace_unknown_card_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["replace", "fact-99", str(tmp_path)])
    assert result.exit_code == 1

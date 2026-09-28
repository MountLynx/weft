"""CLI：weft parse（双模式、闸门、收件箱）。"""
import os
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def _article(root, name="paper.md", text="一篇关于搅拌加速溶解的文章，认为搅拌是主因。"):
    path = root / "articles" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_cli_parse_mock_end_to_end_decompose(tmp_path):
    make_minimal_project(tmp_path)
    source = _article(tmp_path)
    result = runner.invoke(app, ["parse", str(source), str(tmp_path), "--mock"])
    assert result.exit_code == 0, result.output
    assert "已写入 metadata/facts/fact-02.md" in result.output
    assert "claims/cited/claim-02.md" in result.output   # mock match 恒 cited（P11）
    assert (tmp_path / "articles" / "processed" / "paper.md").is_file()
    assert not source.exists()
    report = tmp_path / "generated" / "articles" / "paper-md-report.md"
    assert report.is_file() and "报告" in result.output


def test_cli_parse_mock_end_to_end_literature_note(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "metadata" / "notes" / "key2020.md").unlink()  # mock note 判定为 new
    source = _article(tmp_path)
    result = runner.invoke(app, ["parse", str(source), str(tmp_path),
                                 "--key", "key2020", "--mock"])
    assert result.exit_code == 0, result.output
    assert "已写入 metadata/notes/key2020.md" in result.output
    claim = tmp_path / "metadata" / "claims" / "cited" / "claim-02.md"
    assert claim.is_file()
    assert "key2020" in claim.read_text(encoding="utf-8")   # 次级引用落 cites


def test_cli_parse_rejects_key_not_in_bib(tmp_path):
    make_minimal_project(tmp_path)
    source = _article(tmp_path)
    result = runner.invoke(app, ["parse", str(source), str(tmp_path),
                                 "--key", "ghostkey", "--mock"])
    assert result.exit_code == 1
    assert "E-ARTICLE-KEY" in result.output
    assert source.exists()   # 闸门拒绝，收件箱不动


def test_cli_parse_rejects_file_outside_articles(tmp_path):
    make_minimal_project(tmp_path)
    outside = tmp_path / "elsewhere.md"
    outside.write_text("x", encoding="utf-8")
    result = runner.invoke(app, ["parse", str(outside), str(tmp_path)])
    assert result.exit_code == 1
    assert "articles" in result.output


def test_cli_parse_picks_oldest_without_arg(tmp_path):
    make_minimal_project(tmp_path)
    newer = _article(tmp_path, "new.md")
    older = _article(tmp_path, "old.txt")
    os.utime(newer, (2000000000, 2000000000))
    os.utime(older, (1000000000, 1000000000))
    result = runner.invoke(app, ["parse", str(tmp_path), "--mock"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "articles" / "processed" / "old.txt").is_file()
    assert newer.is_file()   # 只处理最旧的一个（.txt 同样收）


def test_cli_parse_empty_inbox_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["parse", str(tmp_path)])
    assert result.exit_code == 1
    assert "收件箱" in result.output


def test_cli_parse_validation_gate(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-09",
               {"id": "fact-09", "data": ["data-99"], "statement": "s",
                "status": "draft"})
    source = _article(tmp_path)
    result = runner.invoke(app, ["parse", str(source), str(tmp_path), "--mock"])
    assert result.exit_code == 1
    assert "拒绝" in result.output
    assert source.exists()


def test_cli_parse_real_client_failure_is_clean(tmp_path):
    """无配置走真实客户端 → 干净 ERROR，不甩 traceback。"""
    make_minimal_project(tmp_path)
    source = _article(tmp_path)
    result = runner.invoke(app, ["parse", str(source), str(tmp_path)])
    assert result.exit_code == 1
    assert result.output.startswith("ERROR")
    assert "Traceback" not in result.output
    assert source.exists()


def test_cli_parse_non_utf8_article_is_clean_error(tmp_path):
    """GBK/ANSI 编码的文章 → 干净 ERROR，不甩 traceback（Windows 记事本 ANSI 场景）。"""
    make_minimal_project(tmp_path)
    source = _article(tmp_path)
    source.write_bytes("这是 GBK 编码的内容：温度速率。".encode("gbk"))
    result = runner.invoke(app, ["parse", str(source), str(tmp_path), "--mock"])
    assert result.exit_code == 1
    assert result.output.startswith("ERROR")
    assert "Traceback" not in result.output
    assert source.exists()   # 收件箱不动


def test_cli_replace_note_proposal_end_to_end(tmp_path):
    """parse 产出的 note 提案经 weft replace 应用（CLI 级闭环）。"""
    make_minimal_project(tmp_path)
    proposal = tmp_path / "inspirations" / "proposals" / "key2020.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text(
        "---\nid: key2020\nstatus: draft\nsummary: 旧摘要，补充了实验细节。\n"
        'comment: "取代 key2020（文章补充）"\n---\n', encoding="utf-8")
    result = runner.invoke(app, ["replace", "key2020", str(tmp_path)])
    assert result.exit_code == 0, result.output
    new_text = (tmp_path / "metadata" / "notes" / "key2020.md").read_text(encoding="utf-8")
    assert "实验细节" in new_text
    assert (tmp_path / "archive" / "cards" / "notes" / "key2020.md").is_file()
    assert not proposal.exists()

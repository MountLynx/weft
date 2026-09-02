"""render：quarto 子进程封装（M3 设计 §5）。测试全 monkeypatch，不依赖 quarto 安装。"""
import subprocess

import pytest

from weft.render import QuartoNotFoundError, QuartoRenderError, render_paper


def test_render_paper_invokes_quarto_with_defaults(monkeypatch, tmp_path):
    (tmp_path / "paper.qmd").write_text("# T\n", encoding="utf-8")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("weft.render.shutil.which", lambda name: "quarto.exe")
    monkeypatch.setattr("weft.render.subprocess.run", fake_run)
    out = render_paper(tmp_path)
    assert seen["cmd"] == ["quarto.exe", "render", "paper.qmd", "--to", "docx"]
    assert seen["cwd"] == tmp_path
    assert out == tmp_path / "paper.docx"


def test_render_paper_passes_format_through(monkeypatch, tmp_path):
    (tmp_path / "paper.qmd").write_text("# T\n", encoding="utf-8")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("weft.render.shutil.which", lambda name: "quarto")
    monkeypatch.setattr("weft.render.subprocess.run", fake_run)
    out = render_paper(tmp_path, to="html")
    assert seen["cmd"][-1] == "html"
    assert out == tmp_path / "paper.html"


def test_render_paper_quarto_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("weft.render.shutil.which", lambda name: None)
    with pytest.raises(QuartoNotFoundError, match="quarto.org"):
        render_paper(tmp_path)


def test_render_paper_quarto_failure_carries_output(monkeypatch, tmp_path):
    (tmp_path / "paper.qmd").write_text("# T\n", encoding="utf-8")
    monkeypatch.setattr("weft.render.shutil.which", lambda name: "quarto")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    monkeypatch.setattr("weft.render.subprocess.run", fake_run)
    with pytest.raises(QuartoRenderError, match="boom"):
        render_paper(tmp_path)


def test_render_paper_missing_paper_qmd(monkeypatch, tmp_path):
    # 钉 which 保证无 quarto 的机器也走到"缺 paper"分支（测试密封性）
    monkeypatch.setattr("weft.render.shutil.which", lambda name: "quarto")
    with pytest.raises(QuartoRenderError, match="weft assemble"):
        render_paper(tmp_path)

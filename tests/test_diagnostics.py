from weft.diagnostics import Diagnostic, Level


def test_error_is_error():
    d = Diagnostic(Level.ERROR, "E-X", "metadata/data/data-01.md", "refs", "消息")
    assert d.is_error


def test_warning_is_not_error():
    d = Diagnostic(Level.WARNING, "W-X", "metadata/data/data-01.md", None, "消息")
    assert not d.is_error


def test_field_optional():
    d = Diagnostic(Level.ERROR, "E-X", ".", None, "全局消息")
    assert d.field is None

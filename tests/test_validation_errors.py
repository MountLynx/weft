from weft.models.cards import ClaimCard, DataCard, FactCard, MethodCard, NoteCard, ParamCard
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativePart, Node, Use
from weft.validation import validate_project
from tests.helpers import build_project


def _errors(diagnostics):
    return [d for d in diagnostics if d.is_error]


def _one_error_code(diagnostics):
    codes = [d.code for d in _errors(diagnostics)]
    assert len(codes) == 1
    return codes[0]


def test_clean_project_has_no_diagnostics(tmp_path):
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "fig-01a.png").write_bytes(b"x")
    project = build_project(
        root=tmp_path,
        data=[DataCard(id="data-01", status="approved", refs=["fig-01a"])],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        supports=["claim-01"], status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                          status="approved")],
        figures={"fig-01": FigureEntry(caption="c", subfigs={"a": "s"})},
        bib_keys={"key2020"},
        parts=[NarrativePart(id="sec-01", section="Results", nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )
    assert validate_project(project) == []


def test_dangling_data_ref():
    facts = [FactCard(id="fact-01", data=["data-99"], statement="s", status="approved")]
    project = build_project(facts=facts)
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-DANGLING-REF"
    err = _errors(diagnostics)[0]
    assert err.field == "data"
    assert "data-99" in err.message
    assert err.path == "metadata/fact-01.md"


def test_dangling_supports_ref():
    facts = [FactCard(id="fact-01", data=["data-01"], statement="s",
                      supports=["claim-99"], status="approved")]
    data = [DataCard(id="data-01", status="approved")]
    project = build_project(data=data, facts=facts)
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-DANGLING-REF"
    assert _errors(diagnostics)[0].field == "supports"


def test_uses_must_point_at_fact_or_claim():
    # data 卡存在，但 uses 不允许指向 data（spec §2：叙事节点只引用 fact/claim）
    sections = [NarrativePart(id="sec-01", section="R", nodes=[
        Node(id="para-01-01", purpose="describe",
             uses=[Use(id="data-01", role="evidence")], status="approved")])]
    data = [DataCard(id="data-01", status="approved")]
    project = build_project(data=data, parts=sections)
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-DANGLING-REF"
    assert "uses" in _errors(diagnostics)[0].field


def test_cites_not_in_bib():
    claims = [ClaimCard(id="claim-01", claim_type="cited", statement="s",
                        cites=["ghostkey"], status="approved")]
    project = build_project(claims=claims, bib_keys={"real2020"})
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-CITES-NOT-IN-BIB"
    assert _errors(diagnostics)[0].field == "cites"


def test_note_key_not_in_bib():
    project = build_project(notes=[NoteCard(id="ghost2020", summary="s", status="approved")],
                            bib_keys=set())
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-NOTE-NOT-IN-BIB"
    assert _errors(diagnostics)[0].field == "id"


def test_refs_not_in_figures():
    data = [DataCard(id="data-01", status="approved", refs=["fig-99z"])]
    project = build_project(data=data)
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-REFS-NOT-IN-FIGURES"
    assert _errors(diagnostics)[0].field == "refs"


def test_subfig_ref_valid_only_when_listed():
    # fig-01b 未在 subfigs 中列出 → 无效
    data = [DataCard(id="data-01", status="approved", refs=["fig-01b"])]
    figures = {"fig-01": FigureEntry(caption="c", subfigs={"a": "s"})}
    project = build_project(data=data, figures=figures)
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-REFS-NOT-IN-FIGURES"


def test_parent_ref_and_subfig_ref_both_valid():
    data = [DataCard(id="data-01", status="approved", refs=["fig-01a", "fig-01"]),
            DataCard(id="data-02", status="approved", refs=["tbl-01"])]
    figures = {"fig-01": FigureEntry(caption="c", subfigs={"a": "s"}),
               "tbl-01": FigureEntry(caption="t")}
    project = build_project(data=data, figures=figures)
    errors = _errors(validate_project(project))
    assert [d.code for d in errors if d.code == "E-REFS-NOT-IN-FIGURES"] == []


def test_uses_may_point_at_method_or_param():
    # v1.1 §3.5：uses 目标扩展到 method/param，合法引用零诊断
    sections = [NarrativePart(id="sec-01", section="R", nodes=[
        Node(id="para-01-01", purpose="describe",
             uses=[Use(id="qpcr", role="evidence"),
                   Use(id="qpcr-main", role="evidence")], status="approved")])]
    project = build_project(
        methods=[MethodCard(id="qpcr", statement="s", protocol="p",
                            status="approved")],
        params=[ParamCard(id="qpcr-main", method="qpcr", status="approved")],
        parts=sections)
    assert validate_project(project) == []


def test_param_method_dangling_is_error():
    project = build_project(
        params=[ParamCard(id="qpcr-main", method="ghost", status="approved")])
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-DANGLING-REF"
    assert _errors(diagnostics)[0].field == "method"


def test_derived_from_not_in_bib_is_error():
    project = build_project(
        methods=[MethodCard(id="qpcr", statement="s", protocol="p",
                            derived_from=["ghost2025"], status="approved")],
        params=[ParamCard(id="qpcr-main", method="qpcr",
                          derived_from=["ghost2026"], status="approved")])
    diagnostics = validate_project(project)
    assert [d.code for d in _errors(diagnostics)] == \
        ["E-DERIVED-FROM-NOT-IN-BIB", "E-DERIVED-FROM-NOT-IN-BIB"]
    assert {d.field for d in _errors(diagnostics)} == {"derived_from"}

from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection, Node, Use
from weft.validation import validate_project
from tests.helpers import build_project


def _codes(diagnostics):
    return [d.code for d in diagnostics]


def _fact_used_by_narrative():
    return (
        [FactCard(id="fact-01", data=["data-01"], statement="s", status="approved")],
        [NarrativeSection(id="sec-01", section="R", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )


def test_cited_without_cites_warns():
    claims = [ClaimCard(id="claim-01", claim_type="cited", statement="s",
                        status="approved")]
    project = build_project(claims=claims)
    assert "W-CLAIM-CITED-NO-CITES" in _codes(validate_project(project))


def test_rejected_claim_skips_warnings_but_not_errors():
    claims = [ClaimCard(id="claim-01", claim_type="cited", statement="s",
                        cites=["ghostkey"], status="rejected")]
    project = build_project(claims=claims, bib_keys=set())
    diagnostics = validate_project(project)
    assert "W-CLAIM-CITED-NO-CITES" not in _codes(diagnostics)
    # 错误不受 rejected 豁免（设计决策 2）
    assert "E-CITES-NOT-IN-BIB" in _codes(diagnostics)


def test_uncited_claim_without_fact_support_warns():
    claims = [ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                        status="approved")]
    project = build_project(claims=claims)
    assert "W-CLAIM-UNSUPPORTED" in _codes(validate_project(project))


def test_supported_claim_no_warning():
    claims = [ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                        status="approved")]
    facts = [FactCard(id="fact-01", data=["data-01"], statement="s",
                      supports=["claim-01"], status="approved")]
    project = build_project(data=[DataCard(id="data-01", status="approved")],
                            facts=facts, claims=claims)
    assert "W-CLAIM-UNSUPPORTED" not in _codes(validate_project(project))


def test_unsupported_ignores_rejected_facts():
    claims = [ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                        status="draft")]
    facts = [FactCard(id="fact-01", data=["data-01"], statement="s",
                      supports=["claim-01"], status="rejected")]
    project = build_project(data=[DataCard(id="data-01", status="approved")],
                            facts=facts, claims=claims)
    assert "W-CLAIM-UNSUPPORTED" in _codes(validate_project(project))


def test_orphan_data_warns():
    data = [DataCard(id="data-01", status="approved")]
    project = build_project(data=data)
    assert "W-ORPHAN" in _codes(validate_project(project))


def test_data_reachable_via_fact_not_orphan():
    facts, sections = _fact_used_by_narrative()
    project = build_project(data=[DataCard(id="data-01", status="approved")],
                            facts=facts, sections=sections)
    assert "W-ORPHAN" not in _codes(validate_project(project))


def test_claim_reached_only_via_supports_is_used():
    # fact-01 被叙事使用，其 supports 的 claim-01 算可达 → 非孤儿（设计决策 1）
    claims = [ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                        status="approved")]
    facts = [FactCard(id="fact-01", data=["data-01"], statement="s",
                      supports=["claim-01"], status="approved")]
    sections = [NarrativeSection(id="sec-01", section="R", order=1, nodes=[
        Node(id="para-01-01", purpose="describe",
             uses=[Use(id="fact-01", role="evidence")], status="approved")]),
    ]
    project = build_project(data=[DataCard(id="data-01", status="approved")],
                            facts=facts, claims=claims, sections=sections)
    assert "W-ORPHAN" not in _codes(validate_project(project))


def test_figure_file_missing_only_for_fig_refs(tmp_path):
    (tmp_path / "figures").mkdir()
    data = [DataCard(id="data-01", status="approved", refs=["fig-01a", "tbl-01"])]
    figures = {"fig-01": FigureEntry(caption="c", subfigs={"a": "s"}),
               "tbl-01": FigureEntry(caption="t")}
    project = build_project(root=tmp_path, data=data, figures=figures)
    codes = _codes(validate_project(project))
    assert codes.count("W-FIGURE-FILE-MISSING") == 1  # 只查 fig-01a；tbl-01 不查文件


def test_figure_file_present_no_warning(tmp_path):
    fig_dir = tmp_path / "figures"
    fig_dir.mkdir()
    (fig_dir / "fig-01a.png").write_bytes(b"x")
    facts, sections = _fact_used_by_narrative()
    project = build_project(
        root=tmp_path,
        data=[DataCard(id="data-01", status="approved", refs=["fig-01a"])],
        facts=facts, figures={"fig-01": FigureEntry(caption="c", subfigs={"a": "s"})},
        sections=sections)
    assert "W-FIGURE-FILE-MISSING" not in _codes(validate_project(project))


def test_unused_figure_entry_warns():
    data = [DataCard(id="data-01", status="approved", refs=["fig-01a"])]
    figures = {"fig-01": FigureEntry(caption="c", subfigs={"a": "s"}),
               "fig-02": FigureEntry(caption="没人用")}
    project = build_project(data=data, figures=figures)
    diagnostics = validate_project(project)
    unused = [d for d in diagnostics if d.code == "W-FIGURE-UNUSED"]
    assert len(unused) == 1
    assert unused[0].field == "fig-02"
    assert unused[0].path == "metadata/figures.yaml"


def test_note_without_summary_warns():
    project = build_project(notes=[NoteCard(id="k2020", status="approved")],
                            bib_keys={"k2020"})
    diagnostics = validate_project(project)
    warn = [d for d in diagnostics if d.code == "W-NOTE-NO-SUMMARY"]
    assert len(warn) == 1 and warn[0].field == "summary"


def test_note_missing_for_cited_key_warns():
    # §3.4：key 在 bib 但无 note 卡 → 提醒
    claims = [ClaimCard(id="claim-01", claim_type="cited", statement="s",
                        cites=["real2020"], status="approved")]
    project = build_project(claims=claims, bib_keys={"real2020"})
    diagnostics = validate_project(project)
    warn = [d for d in diagnostics if d.code == "W-NOTE-MISSING"]
    assert len(warn) == 1
    assert "real2020" in warn[0].message


def test_purpose_and_role_vocab_warnings():
    facts, sections = _fact_used_by_narrative()
    sections = [NarrativeSection(id="sec-01", section="R", order=1, nodes=[
        Node(id="para-01-01", purpose="speculate",
             uses=[Use(id="fact-01", role="vibe")], status="approved")]),
    ]
    project = build_project(data=[DataCard(id="data-01", status="approved")],
                            facts=facts, sections=sections)
    codes = _codes(validate_project(project))
    assert "W-PURPOSE-VOCAB" in codes
    assert "W-ROLE-VOCAB" in codes


def test_diagnostics_sorted_errors_first_by_path():
    # 排序契约：错误在前（Task 12 CLI 输出依赖），错误内按 path 排序
    from weft.diagnostics import Level
    data = [DataCard(id="data-02", status="approved", refs=["fig-99z"])]
    facts = [FactCard(id="fact-01", data=["data-99"], statement="s", status="approved")]
    project = build_project(data=data, facts=facts)
    diagnostics = validate_project(project)
    assert any(not d.is_error for d in diagnostics)  # 确有提醒参与排序
    levels = [d.level for d in diagnostics]
    assert levels == sorted(levels, key=lambda lv: 0 if lv is Level.ERROR else 1)
    error_paths = [d.path for d in diagnostics if d.is_error]
    assert error_paths == sorted(error_paths)

"""PR #1 review: an optimistic numerical estimate cannot establish compliance."""

from io import BytesIO

import pytest
from pypdf import PdfReader

from shieldlab.physics import barriers as ba, beams as bm, optimize, solver, sources as src
from shieldlab.regulatory import limits as reg
from shieldlab.report import report
from ui.calculator_results import CalculatorAssessment, _decision_status


def _case(model):
    beam = bm.Beam(kind=bm.KIND_DIAGNOSTIC, component="secondary", kvp=120)
    source = src.SourceTerm("diagnostic", "mGy/week", "week",
                            [src.Component("secondary", 1.0, beam)])
    if model == "ct":
        source = src.ct_source([src.CTExamWorkload("head", 1200, 30)], 2)
    barrier = ba.Barrier().add("concrete", 300)
    if model == "mixed":
        barrier.add("lead", 2)
    if model == "narrow":
        barrier = ba.Barrier().add("brick", 500)
    return source, barrier


@pytest.mark.parametrize("model", ["ct", "mixed", "narrow"])
def test_unvalidated_model_cannot_pass_even_with_large_numeric_margin(model):
    source, barrier = _case(model)
    goal = reg.design_goal("NCRP", "uncontrolled")
    evaluation = solver.evaluate(source, barrier, goal)
    assert evaluation.verdict.margin_ratio > 1.2
    assert not evaluation.verdict.acceptable
    assert evaluation.verdict.review_reasons
    assert _decision_status(CalculatorAssessment(source, barrier, goal, evaluation)) == "REVIEW"


def test_model_review_survives_html_and_pdf_exports():
    source, barrier = _case("mixed")
    goal = reg.design_goal("NCRP", "uncontrolled")
    evaluation = solver.evaluate(source, barrier, goal)
    exports = dict(source=source, barrier=barrier, goal=goal, evaluation=evaluation, inputs={})
    html = report.build_html(**exports)
    pdf = PdfReader(BytesIO(report.build_pdf_summary(**exports)))
    pdf_text = " ".join(page.extract_text() for page in pdf.pages)
    assert "REVIEW REQUIRED" in html and "REVIEW REQUIRED" in pdf_text
    assert "Mixed-material" in html and "Mixed-material" in pdf_text
    assert len(pdf.pages) == 1
    assert '<div class="verdict">PASS</div>' not in html


def test_numerical_failure_stays_fail_when_model_also_needs_review():
    source, barrier = _case("mixed")
    goal = reg.design_goal("NCRP", "uncontrolled", override_P_weekly=1e-30)
    verdict = solver.evaluate(source, barrier, goal).verdict
    assert verdict.status == "FAIL"
    assert not verdict.acceptable
    assert verdict.review_reasons


def test_supported_single_material_retains_pass():
    source, barrier = _case("single")
    goal = reg.design_goal("NCRP", "uncontrolled")
    verdict = solver.evaluate(source, barrier, goal).verdict
    assert verdict.status == "PASS"
    assert verdict.acceptable


def test_ct_options_cannot_receive_design_recommendation_badges():
    source, _ = _case("ct")
    options = optimize.rank_options(source, reg.design_goal("NCRP", "uncontrolled"))
    assert options
    assert all(option.review_required for option in options)
    assert not any(o.is_cheapest or o.is_lightest or o.is_thinnest for o in options)
    assert optimize.headline(options) is None


@pytest.mark.parametrize("thickness", [-1, float("nan"), float("inf")])
def test_invalid_layer_thickness_is_rejected(thickness):
    with pytest.raises(ValueError, match="finite and non-negative"):
        ba.Barrier().add("lead", thickness)

"""Colour is never the only carrier of a verdict, and decades are read spatially.

Covers the Track A subset of the workspace design: the decade rail, the drawn
verdict marks, and the plan diagram's non-colour status encoding. These are
presentation rules with a safety purpose -- a submission binder is photocopied in
greyscale, and a reader with a colour-vision deficiency must reach the same verdict
as everyone else.
"""

from __future__ import annotations

import re

import pytest

from shieldlab.room import diagram
from shieldlab.room.engines import AnalyticalEngine, SurrogateEngine
from shieldlab.room.model import AdjacentArea, RoomDesign
from ui import room_results as rr


def _room(thickness_mm: float = 120.0) -> RoomDesign:
    design = RoomDesign.default()
    design.source.isotope = "F-18"
    design.source.activity_MBq = 370.0
    design.room.width_m, design.room.length_m = 7.0, 5.0
    design.source.x_m, design.source.y_m = 3.5, 2.5
    for wall in design.walls:
        wall.material1 = "concrete"
        wall.thickness1_mm = thickness_mm
    design.wall("N").thickness1_mm = 400.0
    design.wall("N").adjacent = AdjacentArea("Control", 1.0, "controlled", None)
    return design


@pytest.fixture
def assessment():
    design = _room()
    return rr.build_assessment(design, "check", SurrogateEngine(design))


# --- the decade rail --------------------------------------------------------

def test_rail_axis_is_shared_by_every_row(assessment):
    """A per-row axis would make two rows incomparable, which defeats the column."""
    low_exp, high_exp = rr.rail_bounds(assessment)
    assert high_exp - low_exp >= 2, "the axis must span at least two decades"

    for index, analytical in enumerate(assessment.analytical_results):
        decision = rr._decision_result_at(assessment, index, analytical)
        if decision.dose_mSv_wk is None:
            continue
        assert 10 ** low_exp <= decision.dose_mSv_wk <= 10 ** high_exp
        assert 10 ** low_exp <= decision.goal_over_T <= 10 ** high_exp


def test_rail_positions_stay_inside_the_track(assessment):
    html = rr.results_table_html(assessment)
    positions = [float(v) for v in re.findall(r"inset-inline-start:([\d.]+)%", html)]
    widths = [float(v) for v in re.findall(r"width:([\d.]+)%", html)]
    assert positions, "the rail should place at least one marker"
    assert all(0.0 <= value <= 100.0 for value in positions)
    assert all(0.0 <= value <= 100.0 for value in widths)


def test_every_evaluated_row_draws_a_rail(assessment):
    html = rr.results_table_html(assessment)
    assert html.count('class="sl-rail"') == len(assessment.analytical_results)
    assert "sl-rail-goal" in html and "sl-rail-decision" in html


def test_the_breach_hatch_appears_only_when_the_interval_crosses_the_goal(assessment):
    """The hatched segment is the whole point: it marks a pass a reviewer shouldn't sign."""
    crossing = 0
    for index, analytical in enumerate(assessment.analytical_results):
        decision = rr._decision_result_at(assessment, index, analytical)
        _low, high = rr._interval_doses(decision)
        if high is not None and decision.goal_over_T and high > decision.goal_over_T:
            crossing += 1
    assert rr.results_table_html(assessment).count("sl-rail-breach") == crossing


def test_rail_survives_a_row_that_could_not_be_evaluated(assessment):
    """A duct has no analytical dose; the column must render, not raise."""
    class _Unevaluated:
        dose_mSv_wk = None
        goal_over_T = None
        ci_low = ci_high = B_achieved = None
        ood = False

    html = rr._rail_html(_Unevaluated(), _Unevaluated(), -4.0, 0.0)
    assert 'class="sl-rail"' in html
    assert "sl-rail-decision" not in html


def test_interval_doses_scale_the_transmission_interval_onto_the_dose_axis():
    class _Result:
        dose_mSv_wk = 0.02
        B_achieved = 0.004
        ci_low = 0.001
        ci_high = 0.016

    low, high = rr._interval_doses(_Result())
    assert low == pytest.approx(0.005)     # 0.001 / 0.004 * 0.02
    assert high == pytest.approx(0.08)     # 0.016 / 0.004 * 0.02


def test_rail_legend_names_every_mark():
    legend = rr.rail_legend_html()
    for key in ("goal", "tick", "dot", "ci", "breach"):
        assert f"sl-rail-key {key}" in legend


# --- verdict marks ----------------------------------------------------------

@pytest.mark.parametrize("status", ["pass", "review", "fail"])
def test_every_verdict_carries_a_drawn_mark(status):
    glyph = rr.status_glyph_svg(status)
    assert glyph.startswith("<svg") and "sl-status-glyph" in glyph
    assert 'aria-hidden="true"' in glyph, "the word beside it is the accessible name"


def test_unknown_status_degrades_to_no_mark():
    assert rr.status_glyph_svg("not-a-status") == ""


def test_status_marks_are_distinct_from_each_other():
    marks = {rr.status_glyph_svg(s) for s in ("pass", "review", "fail")}
    assert len(marks) == 3


def test_table_pairs_each_mark_with_its_word(assessment):
    html = rr.results_table_html(assessment)
    chips = re.findall(r'<span class="sl-table-status \w+">(.*?)</span>', html)
    assert chips
    for chip in chips:
        assert "<svg" in chip, "a verdict must be drawn as well as written"
        assert re.search(r"</svg>\s*\S", chip), "the word must follow the mark"


# --- the plan diagram -------------------------------------------------------

def test_every_non_pass_status_is_encoded_without_colour():
    """Pass is the only solid stroke; everything else is struck or hatched."""
    for status in diagram.STATUS_COLOR:
        if status == "pass":
            assert status not in diagram.STATUS_OVERSTRIKE
            assert status not in diagram.STATUS_LEGEND_HATCH
        else:
            assert status in diagram.STATUS_OVERSTRIKE
            assert status in diagram.STATUS_LEGEND_HATCH


def test_failure_is_encoded_more_densely_than_review():
    assert (len(diagram.STATUS_LEGEND_HATCH["fail"])
            > len(diagram.STATUS_LEGEND_HATCH["review"]))


def test_plan_renders_with_a_failing_and_a_passing_wall():
    design = _room()
    analytical = AnalyticalEngine(design).evaluate_all("check")
    surrogate = SurrogateEngine(design).evaluate_all("check", analytical)
    verdicts = {
        result.passes for result in surrogate if result.label.startswith("Wall")
    }
    assert {True, False} <= verdicts, "the fixture should mix passing and failing walls"

    png = diagram.render(design, surrogate)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 4000

"""A wall of three layers: E-Domain-5's merge rule and correction, and how model E's tier serves it."""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pytest  # noqa: E402

from shieldlab.room import merge_rule as mr  # noqa: E402
from shieldlab.room.engines import AnalyticalEngine, SurrogateEngine  # noqa: E402
from shieldlab.room.model import AdjacentArea, RoomDesign, Wall  # noqa: E402

GYPSUM, LEAD = 2.32, 11.35


def test_two_layers_pass_through():
    wall = [("concrete", 100.0, 2.30), ("lead", 2.0, LEAD)]
    assert mr.merge(wall) == wall
    assert mr.moved_light_mass(wall) == 0.0


def test_board_lead_board_merges_the_boards_in_front():
    # equal boards tie, so the merged board takes the place nearer the source
    merged = mr.merge([("gypsum", 5.0, GYPSUM), ("lead", 2.0, LEAD), ("gypsum", 5.0, GYPSUM)])
    assert merged == [("gypsum", pytest.approx(10.0), GYPSUM), ("lead", 2.0, LEAD)]
    # the back board's 1.16 g/cm2 moved toward the source
    assert mr.moved_light_mass([("gypsum", 5.0, GYPSUM), ("lead", 2.0, LEAD),
                                ("gypsum", 5.0, GYPSUM)]) == pytest.approx(5.0 * GYPSUM / 10.0)


def test_mixed_light_layers_become_concrete_behind_the_heaviest():
    wall = [("gypsum", 5.0, GYPSUM), ("lead", 1.0, LEAD), ("concrete", 100.0, 2.30)]
    merged = mr.merge(wall)
    assert merged[0] == ("lead", 1.0, LEAD)
    assert merged[1][0] == "concrete"
    assert merged[1][1] == pytest.approx((5.0 * GYPSUM + 100.0 * 2.30) / 2.30)
    assert mr.moved_light_mass(wall) == pytest.approx(-5.0 * GYPSUM / 10.0)


def test_walls_outside_the_rule_are_refused():
    with pytest.raises(ValueError):
        mr.merge([("lead", 1.0, LEAD), ("concrete", 100.0, 2.30), ("lead", 1.0, LEAD)])
    with pytest.raises(ValueError):
        mr.merge([("steel", 2.0, 7.87), ("concrete", 100.0, 2.30), ("gypsum", 5.0, GYPSUM)])


def test_correction_is_the_fitted_line_and_held_outside():
    a, b = mr.CORRECTION[364.0]
    assert mr.log10_correction(364.0, 2.0) == pytest.approx(a + 2.0 * b)
    assert mr.log10_correction(637.0, 1.0) == pytest.approx(mr.log10_correction(511.0, 1.0))
    assert mr.log10_correction(100.0, 1.0) == pytest.approx(mr.log10_correction(140.5, 1.0))


def test_the_third_layer_round_trips_through_json():
    design = RoomDesign.default()
    wall = design.wall("N")
    wall.material2, wall.thickness2_mm, wall.material3, wall.thickness3_mm = "lead", 2.0, "gypsum", 15.0
    again = RoomDesign.from_json(design.to_json()).wall("N")
    assert again.layers() == [("concrete", 150.0), ("lead", 2.0), ("gypsum", 15.0)]
    # a third layer counts only behind a second one
    assert Wall(material3="gypsum", thickness3_mm=15.0).layers() == [("concrete", 150.0)]


def _room(*layers, isotope="Tc-99m"):
    design = RoomDesign.default()
    design.source.isotope = isotope
    design.room.width_m, design.room.length_m = 7.0, 5.0
    design.source.x_m, design.source.y_m = 3.5, 2.5
    (m1, t1), (m2, t2), (m3, t3) = (list(layers) + [(None, 0.0)] * 2)[:3]
    for wall in design.walls:
        wall.material1, wall.thickness1_mm = m1, t1
        wall.material2, wall.thickness2_mm = m2, t2
        wall.material3, wall.thickness3_mm = m3, t3
    design.wall("N").adjacent = AdjacentArea("Control", 1.0, "controlled", None)
    return design


def _wall_n(design):
    engine = SurrogateEngine(design)
    if not engine.available():
        pytest.skip("no surrogate bundle loaded")
    results = engine.evaluate_all("check", AnalyticalEngine(design).evaluate_all("check"))
    return {r.label: r for r in results}["Wall N"]


def test_a_lined_partition_is_served_as_its_merged_wall_divided_by_c():
    # 15 mm boards (0.80 g/cm3) either side of 2 mm lead, against the wall the rule turns it into:
    # 30 mm of board in front of the lead. Tc-99m is one line, at 140.5 keV.
    three = _wall_n(_room(("gypsum", 15.0), ("lead", 2.0), ("gypsum", 15.0)))
    two = _wall_n(_room(("gypsum", 30.0), ("lead", 2.0)))
    assert three.engine == two.engine == "surrogate"
    moved = 15.0 * 0.80 / 10.0
    expected = -mr.log10_correction(140.5, moved)
    assert math.log10(three.B_achieved) - math.log10(two.B_achieved) == pytest.approx(expected, abs=1e-9)
    assert math.log10(three.ci_high) - math.log10(two.ci_high) == pytest.approx(expected, abs=1e-9)
    assert "Three layers served as" in three.note


def test_a_wall_outside_the_rule_uses_the_analytical_tier():
    result = _wall_n(_room(("lead", 1.0), ("concrete", 100.0), ("lead", 1.0)))
    assert result.engine == "analytical (OOD fallback)"
    assert "merge rule" in result.note
    assert result.B_achieved is not None


def test_the_analytical_tier_counts_the_third_layer():
    def wall_n(*layers):
        results = AnalyticalEngine(_room(*layers)).evaluate_all("check")
        return {r.label: r for r in results}["Wall N"].B_achieved

    assert wall_n(("concrete", 100.0), ("lead", 1.0), ("concrete", 50.0)) < \
        wall_n(("concrete", 100.0), ("lead", 1.0))

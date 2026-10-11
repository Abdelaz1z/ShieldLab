"""
Survey of a drawn room (shieldlab.room.drawn_plan / drawn_survey).

A square room drawn in Room Designer must give, through one wall at normal incidence, the same
transmission as the rectangular Room Designer gives for that wall: both ask the same engines about
the same barrier, and only the distance differs (the drawn wall has a thickness, the rectangle's
inner face does not).

    py -3 tests\\test_drawn_survey.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shieldlab.room.drawn_plan import parse_plan
from shieldlab.room.drawn_survey import SurveySetup, calculation_point, crossed_sides, survey
from shieldlab.room.engines import AnalyticalEngine, SurrogateEngine
from shieldlab.room.model import Room, RoomDesign, Source

CONCRETE_200 = (("concrete", 200.0),)


def _plan(markers, openings=(), inner=None):
    """A 4 m x 4 m outline (20 cm walls, 1 unit = 1 cm), the source at its centre."""
    walls = [{"id": "w_out", "kind": "outline", "closed": True, "thickness": 20, "segThickness": {},
              "points": [{"x": 0, "y": 0}, {"x": 400, "y": 0}, {"x": 400, "y": 400},
                         {"x": 0, "y": 400}]}]
    if inner:
        walls.append(inner)
    return {"name": "test", "settings": {"wallThickness": 14, "unitsPerMeter": 100},
            "walls": walls, "openings": list(openings),
            "items": [{"type": "trefoil", "x": 200, "y": 200}],
            "markers": [{"n": n, "x": x, "y": y, "label": ""} for n, (x, y) in enumerate(markers, 1)]}


def _setup(**walls):
    keys = ("W1.1", "W1.2", "W1.3", "W1.4")
    return SurveySetup(isotope="F-18", activity_MBq=370.0, patients_per_week=40.0,
                       residence_min=60.0, walls={k: walls.get(k, CONCRETE_200) for k in keys})


def test_point_at_a_wall_moves_beyond_it():
    plan = parse_plan(_plan([(200, -25)]))                   # drawn just outside side 1 (y = 0)
    calc, moved = calculation_point(plan, plan.sources[0], plan.points[0])
    assert moved is not None and moved.key == "W1.1"
    assert math.isclose(calc[1], -0.1 - 0.3) and math.isclose(calc[0], 2.0)


def test_normal_incidence_matches_the_rectangular_room():
    plan = parse_plan(_plan([(200, -25)]))
    result = survey(plan, _setup())[0]
    assert len(result.crossings) == 1 and result.crossings[0].angle_deg < 1e-6

    rect = RoomDesign.default()
    rect.room = Room(width_m=4.0, length_m=4.0)
    rect.source = Source(isotope="F-18", activity_MBq=370.0, patients_per_week=40.0,
                         residence_min=60.0, x_m=2.0, y_m=2.0)
    for wall in rect.walls:
        wall.material1, wall.thickness1_mm = "concrete", 200.0
    analytical = AnalyticalEngine(rect).evaluate_all("check")
    reference = next(r for r in SurrogateEngine(rect).evaluate_all("check", analytical)
                     if r.label == "Wall S")
    assert math.isclose(result.B, reference.B_achieved, rel_tol=1e-9), (result.B, reference.B_achieved)
    # same barrier, so the doses differ only by the inverse square of the two distances
    assert math.isclose(result.distance_m, 2.4)
    assert math.isclose(result.dose_mSv_wk / reference.dose_mSv_wk, (2.3 / 2.4) ** 2, rel_tol=1e-9)


def test_oblique_line_is_thicker_but_corrected_upwards():
    plan = parse_plan(_plan([(200, -25), (40, -25)]))
    normal, oblique = survey(plan, _setup())
    crossing = oblique.crossings[0]
    assert 30.0 < crossing.angle_deg < 70.0
    assert oblique.B < normal.B                                # a longer path through the wall
    if crossing.result.engine == "surrogate":
        assert crossing.oblique_log10 > 0.0                    # scatter's shorter way out


def test_door_replaces_the_wall_where_the_line_passes_through_it():
    door = {"id": "o1", "type": "door", "pathId": "w_out", "seg": 0, "t": 0.5, "width": 90,
            "vision": False}
    plan = parse_plan(_plan([(200, -25)], openings=[door]))
    setup = _setup()
    setup.openings["O1"] = (("lead", 2.0),)
    through_door = survey(plan, setup)[0]
    assert through_door.crossings[0].layers == (("lead", 2.0),)
    assert through_door.B > survey(parse_plan(_plan([(200, -25)])), _setup())[0].B


def test_two_walls_multiply():
    inner = {"id": "w_in", "kind": "partition", "closed": False, "thickness": 10, "segThickness": {},
             "points": [{"x": 0, "y": 100}, {"x": 400, "y": 100}]}
    plan = parse_plan(_plan([(200, -25)], inner=inner))
    setup = _setup()
    setup.walls["W2.1"] = (("gypsum", 100.0),)
    result = survey(plan, setup)[0]
    assert [c.barrier.split(",")[0] for c in result.crossings] == ["Inner wall W2.1", "Outline W1.1"]
    assert math.isclose(result.B, result.crossings[0].result.B_achieved
                        * result.crossings[1].result.B_achieved, rel_tol=1e-12)


def test_line_through_a_corner_counts_one_wall():
    plan = parse_plan(_plan([(-25, -25)]))
    hits = crossed_sides(plan, plan.sources[0], (-0.3, -0.3))
    assert len(hits) == 1


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok", name)

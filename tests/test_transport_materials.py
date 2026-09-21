"""The simulated-material table, and serving a product at the simulated thickness of equal mass."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pytest  # noqa: E402

from shieldlab.room import transport_materials as tm  # noqa: E402
from shieldlab.room.engines import AnalyticalEngine, SurrogateEngine  # noqa: E402
from shieldlab.room.model import AdjacentArea, RoomDesign  # noqa: E402


def test_the_table_is_the_geant4_one():
    # Read from GATE 10.1 / Geant4 11.4.1 in the production container on 2026-09-21. A change
    # here means the physics the models learned has been misdescribed, not that the app improved.
    assert {name: density for name, (_, density) in tm.SIMULATED.items()} == {
        "lead": 11.35, "concrete": 2.30, "steel": 8.00, "gypsum": 2.32,
        "lead_glass": 6.22, "barite_concrete": 3.35, "brick": 1.80,
    }


def test_wallboard_is_served_as_the_solid_gypsum_with_its_mass():
    # 16 mm of 0.80 g/cm3 board carries the mass of 5.52 mm of 2.32 g/cm3 solid gypsum.
    assert tm.simulated_thickness_mm("gypsum", 16.0) == pytest.approx(16.0 * 0.80 / 2.32)


def test_denser_product_concrete_is_served_slightly_thicker():
    assert tm.simulated_thickness_mm("concrete", 100.0) == pytest.approx(100.0 * 2.35 / 2.30)


def test_lead_and_brick_are_unchanged():
    assert tm.simulated_thickness_mm("lead", 4.0) == pytest.approx(4.0)
    assert tm.simulated_thickness_mm("brick", 230.0) == pytest.approx(230.0)


def test_lead_glass_of_another_density_is_not_rescaled():
    # Its lead fraction falls with its density, so equal mass per area is not equal attenuation.
    assert tm.product_density_gcm3("lead_glass") != pytest.approx(6.22, rel=0.005)
    assert tm.simulated_thickness_mm("lead_glass", 20.0) is None


def test_a_material_never_simulated_has_no_simulated_thickness():
    assert tm.simulated_thickness_mm("wood", 50.0) is None


def test_the_note_names_the_conversion_only_when_it_changes_the_wall():
    note = tm.served_as_note([("gypsum", 16.0)])
    assert "5.5 mm of G4_GYPSUM" in note
    assert tm.served_as_note([("lead", 4.0)]) == ""


def _gypsum_room(thickness_mm):
    design = RoomDesign.default()
    design.source.isotope = "I-131"
    design.source.activity_MBq = 370.0
    design.room.width_m, design.room.length_m = 7.0, 5.0
    design.source.x_m, design.source.y_m = 3.5, 2.5
    for wall in design.walls:
        wall.material1 = "gypsum"
        wall.thickness1_mm = thickness_mm
    design.wall("N").adjacent = AdjacentArea("Control", 1.0, "controlled", None)
    return design


def _served_wall(thickness_mm):
    design = _gypsum_room(thickness_mm)
    engine = SurrogateEngine(design)
    if not engine.available():
        pytest.skip("no surrogate bundle loaded")
    results = engine.evaluate_all("check", AnalyticalEngine(design).evaluate_all("check"))
    return {r.label: r for r in results}["Wall N"]


def test_a_wallboard_wall_transmits_like_the_lighter_wall_it_is():
    # 300 mm of 0.80 g/cm3 board is served as 103 mm of solid gypsum. Before the fix it was served
    # as 300 mm of solid gypsum, which is what an 870 mm board is served as now. Both thicknesses
    # sit inside model E's I-131 gypsum range (17.5-591 mm), so the model answers both; realistic
    # 16-32 mm board falls below that range and is refused by the guard either way.
    board = _served_wall(300.0)
    old_serving = _served_wall(300.0 * 2.32 / 0.80)
    for wall in (board, old_serving):
        if wall.ood or wall.B_achieved is None:
            pytest.skip("a reference wall is outside the model's domain")
    assert board.B_achieved > 10.0 * old_serving.B_achieved
    assert "300.0 mm gypsum as 103.4 mm of G4_GYPSUM" in board.note

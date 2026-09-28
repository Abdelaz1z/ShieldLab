"""
Smoke test for the field-map U-Net tier (shieldlab.room.field_surrogate).

Runs two ways:
  * WITHOUT torch installed -> the tier must degrade gracefully (available() is False,
    no import error) so the app still runs.
  * WITH torch + weights present -> loads the model, predicts on the default room, and
    checks the field is finite in air, shaped right, and physically ordered
    (dose falls with distance from the source).

    py -3.11 tests\\test_field_surrogate.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from shieldlab.room.model import RoomDesign
from shieldlab.room import field_surrogate as fs


def test_graceful_and_predict():
    design = RoomDesign.default()
    fm = fs.FieldModel()

    if not fm.available():
        print("torch/weights absent -> tier correctly reports available() == False (graceful).")
        # the design->box mapping must still work without torch:
        box = fs._design_to_box(design)
        assert box.labels.shape == (fs.GRID[2], fs.GRID[1], fs.GRID[0]), box.labels.shape
        assert box.material in fs.TRAINED_MATERIALS
        print(f"design->box OK: material={box.material}, "
              f"walls={tuple(round(t) for t in box.wall_mm)} mm, E={box.energy_keV} keV")
        return

    pred = fm.predict(design)
    assert pred is not None
    ld = pred.log_dose
    assert ld.shape == (fs.GRID[2], fs.GRID[1], fs.GRID[0]), ld.shape
    air = pred.labels == 0
    fin = np.isfinite(ld)
    assert (fin == air).all() or fin.sum() > 0, "field should be finite exactly in air voxels"
    # physical ordering: mean dose in the occupied shell < mean dose near the source
    iz, iy, ix = pred.source_vox
    near = ld[max(iz-2, 0):iz+3, max(iy-2, 0):iy+3, max(ix-2, 0):ix+3]
    near = near[np.isfinite(near)]
    shell = fs._occupied_shell(pred.labels)
    shellvals = ld[shell & np.isfinite(ld)]
    assert near.size and shellvals.size
    assert near.mean() > shellvals.mean(), (near.mean(), shellvals.mean())
    png = fs.render_field_slice(pred, design)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "render should return a PNG"
    print(f"predict OK: material={pred.material}, shell p95 log10={pred.shell_p95_log:.2f}, "
          f"near-source mean {near.mean():.2f} > shell mean {shellvals.mean():.2f} dex, "
          f"PNG {len(png)} bytes")


def _box(material, thickness_mm, isotope):
    """The 2026-09-26 check room: 6 x 5 x 3 m, one material, source at the centre."""
    from shieldlab.room.model import Room, Source
    design = RoomDesign.default()
    design.room = Room(6.0, 5.0, 3.0)
    design.source = Source(isotope=isotope, x_m=3.0, y_m=2.5)
    for wall in design.walls:
        wall.material1, wall.thickness1_mm, wall.material2 = material, thickness_mm, None
    return design


def _in_room_over_primary(fm, design, energy):
    """Predicted kerma over the bare inverse-square primary at 0.3, 0.5, 1 and 2 m east."""
    muen_air = {364.0: 0.02931, 511.0: 0.02966}             # cm^2/g, NIST XCOM
    pred = fm.predict(design)
    iz, iy, ix = pred.source_vox
    out = []
    for r_m in (0.3, 0.5, 1.0, 2.0):
        primary = (energy * 1e-3 * 1.602e-13 * muen_air[energy] * 1e3
                   / (4 * np.pi * (r_m * 100) ** 2))          # Gy per photon
        out.append(10 ** pred.log_dose[iz, iy, ix + int(round(r_m * 10))] / 2e7 / primary)
    return out


def test_in_room_field_follows_inverse_square():
    """Next to a bare source the in-room kerma cannot fall below the primary alone. Lead read
    0.05-0.3x here before its walls were mapped onto a trained material (2026-09-26)."""
    fm = fs.FieldModel()
    if not fm.available():
        print("field model absent -> inverse-square check skipped")
        return
    for material, thickness in (("concrete", 200), ("gypsum", 30), ("lead", 4), ("lead", 14),
                                ("steel", 10), ("lead_glass", 20)):
        for isotope, energy in (("I-131", 364.0), ("F-18", 511.0)):
            ratios = _in_room_over_primary(fm, _box(material, thickness, isotope), energy)
            assert all(0.8 < r < 1.5 for r in ratios), (material, thickness, isotope, ratios)


def test_reference_material_is_its_own_equivalent():
    for isotope in ("I-131", "F-18"):
        eq, _ = fs._equivalent(isotope, "concrete", fs._app_layers("concrete", 200.0))
        assert abs(eq[0] - 200.0) < 10.0, (isotope, eq)


def test_lead_equivalents_are_ordered_and_physical():
    # 4 mm of lead is a few centimetres of concrete at 364 keV, 14 mm about 15-25 cm.
    thin, _ = fs._equivalent("I-131", "concrete", (("lead", 4.0),))
    thick, _ = fs._equivalent("I-131", "concrete", (("lead", 14.0),))
    assert 20.0 < thin[0] < 100.0, thin
    assert 120.0 < thick[0] < 300.0, thick
    assert all(a < b for a, b in zip(thin, thick))


def test_field_beyond_a_wall_follows_its_own_thickness():
    """150 and 200 mm concrete are both built as a 200 mm box; the field beyond them used to be
    identical. It must now be higher behind the thinner wall."""
    fm = fs.FieldModel()
    if not fm.available():
        print("field model absent -> beyond-wall check skipped")
        return
    thin, thick = (fm.predict(_box("concrete", t, "F-18")) for t in (150, 200))
    assert thin.wall_mm == thick.wall_mm
    iz, iy, ix = thin.source_vox
    k = 30 + int(thin.wall_mm[0] / 100) + 5                   # 0.5 m beyond the east wall
    assert thin.log_dose[iz, iy, ix + k] - thick.log_dose[iz, iy, ix + k] > 0.15


def test_field_above_the_ceiling_follows_the_walls():
    """2 and 4 mm lead rooms are both built as a 100 mm box; above the ceiling they read the same
    until the slabs were corrected too (FieldLead-1 MC: the map read 2.1x low over 2 mm lead)."""
    fm = fs.FieldModel()
    if not fm.available():
        print("field model absent -> slab check skipped")
        return
    thin, thick = (fm.predict(_box("lead", t, "F-18")) for t in (2, 4))
    assert thin.wall_mm == thick.wall_mm
    iz, iy, ix = thin.source_vox
    above = iz + 15 + 5                                       # 0.5 m over a 3 m room's ceiling
    assert thin.log_dose[above, iy, ix] - thick.log_dose[above, iy, ix] > 0.05


def test_slab_steps_point_toward_the_equivalent():
    thin = fs._design_to_box(_box("concrete", 150, "F-18"))       # built 200, equivalent ~150
    assert thin.wall_mm[2] == 200 and fs._slab_steps(thin)[0] == -fs.SLOPE_STEP_MM
    lead = fs._design_to_box(_box("lead", 2, "F-18"))             # built 100, cannot step inward
    assert lead.wall_mm[2] == 100 and fs._slab_steps(lead)[0] == fs.SLOPE_STEP_MM


def test_tall_room_says_its_slabs_are_uncorrected():
    """4.6 m inside + 2 x 100 mm fills the 4.8 m domain: neither slab step fits, and the map must
    say so rather than present the slabs as corrected."""
    fm = fs.FieldModel()
    if not fm.available():
        print("field model absent -> tall-room check skipped")
        return
    from shieldlab.room.model import Room
    design = _box("lead", 2, "F-18")
    design.room = Room(6.0, 5.0, 4.6)
    pred = fm.predict(design)
    assert any("floor and ceiling are drawn at a whole" in w for w in pred.warnings), pred.warnings
    assert not any("floor and ceiling are drawn at a whole" in w
                   for w in fm.predict(_box("lead", 2, "F-18")).warnings)


if __name__ == "__main__":
    test_graceful_and_predict()
    test_in_room_field_follows_inverse_square()
    test_reference_material_is_its_own_equivalent()
    test_lead_equivalents_are_ordered_and_physical()
    test_field_beyond_a_wall_follows_its_own_thickness()
    test_field_above_the_ceiling_follows_the_walls()
    test_slab_steps_point_toward_the_equivalent()
    test_tall_room_says_its_slabs_are_uncorrected()
    print("OK")
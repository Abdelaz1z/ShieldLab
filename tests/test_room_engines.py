"""
test_room_engines.py — A6 acceptance gate for the Room Designer analytical engine.
Verifies: (1) Design-mode suggestion matches the ShieldLab v1.0 solver on identical
inputs (±1 mm); (2) Check-mode pass/fail with margins; (3) duct defers to surrogate;
(4) JSON round-trip; (5) all three report exports render.
Run: py -3.11 tests/test_room_engines.py   (also pytest-compatible)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from radshield.room.model import RoomDesign, Opening
from radshield.room.engines import AnalyticalEngine
from radshield.room import diagram, report_room
from radshield.physics import sources as src, solver as sv
from radshield.regulatory import limits as reg


def _golden() -> RoomDesign:
    with open(os.path.join(HERE, "golden_room.json"), encoding="utf-8") as fh:
        return RoomDesign.from_json(fh.read())


def test_design_matches_solver_within_1mm():
    """Engine's Design suggestion == an independent ShieldLab solver call (±1 mm)."""
    d = _golden()
    engN = [r for r in AnalyticalEngine(d).evaluate_all("design") if r.label == "Wall N"][0]

    # independent recomputation of the SAME quantity, wired by hand from known numbers
    d_pop = 2.0 + 0.3                       # perp(N)=length-y=4-2=2
    source = src.radionuclide_point_source(
        "F-18", 370.0 / 37.0, d_m=d_pop, hours_per_week=50 * 60 / 60.0, occupancy=1.0)
    goal = reg.design_goal("NCRP", "controlled", occupancy_T=1.0)
    req = sv.required_thickness(source, "concrete", goal)
    pref = sv.preferred_thickness(req, "concrete")

    assert engN.suggested_thickness_mm == pref, (engN.suggested_thickness_mm, pref)
    assert abs(req - 149.2) < 1.0, req         # frozen reference (ShieldLab v1.0)
    assert engN.suggested_thickness_mm == 150.0


def test_check_pass_fail_and_margin():
    d = _golden()
    # 150 mm concrete on the controlled Wall N should PASS with a small margin
    resN = [r for r in AnalyticalEngine(d).evaluate_all("check") if r.label == "Wall N"][0]
    assert resN.passes is True
    assert resN.margin is not None and resN.margin >= 1.0

    # thin it to 50 mm -> must FAIL, and the deficit shows as margin < 1
    d.wall("N").thickness1_mm = 50.0
    resN2 = [r for r in AnalyticalEngine(d).evaluate_all("check") if r.label == "Wall N"][0]
    assert resN2.passes is False
    assert resN2.margin is not None and resN2.margin < 1.0

    # restore to 150 -> green again (the live-flip behaviour)
    d.wall("N").thickness1_mm = 150.0
    resN3 = [r for r in AnalyticalEngine(d).evaluate_all("check") if r.label == "Wall N"][0]
    assert resN3.passes is True


def test_duct_defers_to_surrogate():
    d = _golden()
    d.wall("N").openings.append(Opening(kind="duct", center_along_wall_m=3.0, radius_mm=25))
    duct = [r for r in AnalyticalEngine(d).evaluate_all("check") if "duct" in r.label][0]
    assert duct.passes is None
    assert duct.dose_mSv_wk is None
    assert "surrogate" in duct.note.lower() or "duct" in duct.note.lower()


def test_json_roundtrip_identical_results():
    d = _golden()
    d2 = RoomDesign.from_json(d.to_json())
    r1 = AnalyticalEngine(d).evaluate_all("check")
    r2 = AnalyticalEngine(d2).evaluate_all("check")
    assert len(r1) == len(r2)
    for a, b in zip(r1, r2):
        assert a.label == b.label
        if a.dose_mSv_wk is None:
            assert b.dose_mSv_wk is None
        else:
            assert abs(a.dose_mSv_wk - b.dose_mSv_wk) < 1e-12


def test_all_three_exports_render():
    d = _golden()
    results = AnalyticalEngine(d).evaluate_all("design")
    png = diagram.render(d, results)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"           # valid PNG signature
    rep = report_room.build_report(d, results, "design", png)
    pdf, _, _ = report_room.export(rep, "PDF")
    xlsx, _, _ = report_room.export(rep, "Excel")
    html, _, _ = report_room.export(rep, "HTML")
    assert pdf[:5] == b"%PDF-"                        # PDF magic
    assert xlsx[:2] == b"PK"                          # xlsx is a zip
    assert b"<html" in html.lower() and b"ShieldLab" in html


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"[PASS] {name}")
            except AssertionError as e:
                fails += 1; print(f"[FAIL] {name}: {e}")
            except Exception as e:
                fails += 1; print(f"[ERROR] {name}: {type(e).__name__}: {e}")
    print("\nALL PASS" if fails == 0 else f"\n{fails} FAILED")
    sys.exit(fails)

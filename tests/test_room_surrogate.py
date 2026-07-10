"""
test_room_surrogate.py — B5 acceptance gate for the surrogate tier (Phase B).
Requires models/surrogate_bundle.joblib + scikit-learn (pinned in requirements.txt).
If the bundle/sklearn is absent the whole suite SKIPS (analytical-only deploys stay green).
Run: py -3.11 tests/test_room_surrogate.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from radshield.room.model import RoomDesign, Opening, AdjacentArea
from radshield.room.engines import AnalyticalEngine, SurrogateEngine


def _room(iso="F-18", mbq=370.0, thickness=200.0, material="concrete"):
    d = RoomDesign.default()
    d.source.isotope = iso
    d.source.activity_MBq = mbq
    d.room.width_m, d.room.length_m = 7.0, 5.0
    d.source.x_m, d.source.y_m = 3.5, 2.5
    for w in d.walls:
        w.material1 = material
        w.thickness1_mm = thickness
    d.wall("N").adjacent = AdjacentArea("Control", 1.0, "controlled", None)
    return d


def _both(d, mode="check"):
    ae = AnalyticalEngine(d)
    se = SurrogateEngine(d)
    ar = ae.evaluate_all(mode)
    sr = se.evaluate_all(mode, ar)
    return se, {r.label: r for r in ar}, {r.label: r for r in sr}


def test_bundle_loads():
    se = SurrogateEngine(_room())
    assert se.available(), "surrogate_bundle.joblib did not load"
    assert se.bundle["meta"]["n_accepted"] == 3182
    assert se.bundle["meta"]["cqr95_coverage_holdout"] >= 0.95


def test_solid_wall_envelope():
    """Surrogate B is a valid transmission and, for in-domain solid walls, sits within the
    documented finite-geometry envelope of the analytical value (~0.3-1.5×)."""
    checked = 0
    for iso, thk in [("F-18", 200), ("F-18", 250), ("Tc-99m", 60), ("I-131", 120), ("F-18", 180)]:
        se, am, sm = _both(_room(iso=iso, thickness=thk))
        a, s = am["Wall N"], sm["Wall N"]
        assert 0.0 < s.B_achieved <= 1.0, (iso, thk, s.B_achieved)
        if not s.ood:                     # ratio only meaningful where the surrogate is trusted
            ratio = s.B_achieved / a.B_achieved
            assert 0.3 <= ratio <= 1.6, (iso, thk, ratio)
            checked += 1
    assert checked >= 3, "too few in-domain solid-wall cases to validate the envelope"


def test_deep_wall_triggers_ood_fallback():
    """A deep wall (B < 2e-3) is the excised deep-tail regime -> surrogate must defer to the
    analytical value, never emit a raw prediction."""
    se, am, sm = _both(_room(iso="F-18", thickness=500))
    s = sm["Wall N"]
    assert s.ood is True
    assert "fallback" in s.engine.lower()
    assert s.ci_low is None                       # no raw surrogate interval was used
    assert abs(s.B_achieved - am["Wall N"].B_achieved) < 1e-12   # it IS the analytical value


def test_offaxis_opening_triggers_ood():
    """An opening far off-axis (offset beyond the ~300 mm training box) is out of domain."""
    d = _room(thickness=250)
    d.room.width_m = 10.0
    d.source.x_m = 1.0                            # push the source into a corner
    d.wall("N").openings.append(Opening(kind="window", center_along_wall_m=8.0, lead_equiv_mm=2))
    se, am, sm = _both(d)
    win = [r for k, r in sm.items() if "window" in k][0]
    assert win.ood is True


def test_duct_streaming_beats_solid_wall():
    """On-axis duct: the surrogate gives a real number that far exceeds the solid-wall B
    (the streaming effect the analytical tier cannot represent)."""
    d = _room(thickness=250)
    d.wall("N").openings.append(Opening(kind="duct", center_along_wall_m=3.5, radius_mm=40))
    se, am, sm = _both(d)
    wall, duct = sm["Wall N"], sm["Wall N · duct"]
    assert duct.ood is False
    assert duct.B_achieved is not None and duct.ci_low is not None
    assert duct.B_achieved > 3.0 * wall.B_achieved       # streaming dominates


def test_maze_corner_surrogate():
    """In-domain maze -> screening estimate with a (wide) 95% band; out-of-domain
    corridor -> refused. Report carries the surrogate CI columns."""
    d = _room(iso="I-131", thickness=300)
    d.wall("E").openings.append(Opening(kind="maze", center_along_wall_m=2.5,
                                        ret_material="concrete", ret_thickness_mm=200,
                                        corridor_m=0.8, shadow_offset_m=0.5))
    se, am, sm = _both(d)
    mz = sm["Wall E · maze"]
    assert mz.engine == "corner surrogate", mz.engine
    assert mz.B_achieved is not None and 0 < mz.B_achieved <= 1.0
    assert mz.ci_low is not None and mz.ci_high >= mz.B_achieved >= mz.ci_low

    # out-of-domain corridor (3 m > the 1.5 m study max) -> refused
    d.wall("E").openings[0].corridor_m = 3.0
    se, am, sm = _both(d)
    mz2 = sm["Wall E · maze"]
    assert mz2.ood is True and mz2.B_achieved is None

    # report rows carry the surrogate columns
    from radshield.room import report_room, diagram
    d.wall("E").openings[0].corridor_m = 0.8
    se2 = SurrogateEngine(d)
    ae2 = AnalyticalEngine(d)
    ar2 = ae2.evaluate_all("check")
    sr2 = se2.evaluate_all("check", ar2)
    rep = report_room.build_report(d, ar2, "check", diagram.render(d, sr2),
                                   surrogate_results=sr2)
    row = [r for r in rep["rows"] if "maze" in r["barrier"]][0]
    assert row["surrogate_CI95"] != "—"
    pdf, _, _ = report_room.export(rep, "PDF")
    assert pdf[:5] == b"%PDF-"


if __name__ == "__main__":
    # skip cleanly if the bundle/sklearn is unavailable
    try:
        if not SurrogateEngine(_room()).available():
            print("SKIP: surrogate bundle not available (analytical-only deploy)."); sys.exit(0)
    except Exception as e:
        print(f"SKIP: {e}"); sys.exit(0)
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

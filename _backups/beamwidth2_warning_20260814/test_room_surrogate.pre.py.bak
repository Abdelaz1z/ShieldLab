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

from shieldlab.room.model import RoomDesign, Opening, AdjacentArea
from shieldlab.room.engines import AnalyticalEngine, SurrogateEngine


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
    # Regression guard, not a version lock: the training set only ever GROWS (4,177 rescued
    # full-domain baseline -> +Lu-177 -> +materials tier). A drop means the bundle was rebuilt
    # on a subset — the failure this is here to catch.
    assert se.bundle["meta"]["n_accepted"] >= 4177          # full domain: shadow+deep+boundary rescued
    assert se.bundle["meta"]["n_excised"] == 0              # zero known bias remaining
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


def test_deep_wall_served_with_wide_band():
    """A deep wall (B < 2e-3) WAS the excised deep-tail regime; after the HPC analog rescue the
    surrogate is trained on unbiased labels there and now SERVES it (the excised set is empty),
    under the wider group-conditional (deep-tail) conformal band — an honest inflated interval,
    not a deferral to the analytical value."""
    se, am, sm = _both(_room(iso="F-18", thickness=500))
    s = sm["Wall N"]
    assert s.ood is False                              # no longer routed away
    assert s.engine == "surrogate"
    assert s.ci_low is not None and s.ci_high is not None
    assert 0.0 < s.B_achieved <= 1.0 and s.ci_low <= s.B_achieved <= s.ci_high
    # the deep-tail band must be markedly wider than a thin-wall (standard-group) band
    thin = _both(_room(iso="F-18", thickness=120))[2]["Wall N"]
    deep_rel = s.ci_high / max(s.ci_low, 1e-300)
    thin_rel = thin.ci_high / max(thin.ci_low, 1e-300)
    assert deep_rel > 3.0 * thin_rel


def test_deep_wall_geometry_bias_warning():
    """mu*x > 8: the surrogate must SAY it is biased low there.

    The training labels came from a finite 0.5 m beam, which under-states lateral scatter at
    depth by about x2 (measured: x1.90/x1.81/x2.01 at mu*x 8/10/12). That makes the surrogate
    under-predict dose — the unsafe direction — and neither the OOD guard nor the analytical
    fallback catches it, so the warning is the only mitigation. It must survive refactors, and
    it must be on BOTH surrogate returns: the banded one and the deep-tail one whose interval
    is withdrawn, since the deepest walls of all take the second."""
    from shieldlab.room import engines as eng

    # optical depth is summed over layers, in the app's own mu/rho and density
    mu_per_cm = eng.optical_depth(364.0, [("concrete", 10.0)])          # 10 mm = 1 cm
    assert 0.20 < mu_per_cm < 0.27, mu_per_cm                            # NIST concrete @364 keV
    assert eng.optical_depth(511.0, [("concrete", 250.0), ("lead", 20.0)]) > \
           eng.optical_depth(511.0, [("concrete", 250.0)])
    assert eng.optical_depth(511.0, [("unobtainium", 250.0)]) is None    # unknown -> None, not 0

    shallow = _both(_room(iso="F-18", thickness=200))[2]["Wall N"]       # mu*x ~ 4
    assert shallow.mu_x is not None and shallow.mu_x < eng.GEOMETRY_BIAS_MUX
    assert shallow.geometry_bias is False
    assert eng.GEOMETRY_BIAS_WARNING not in shallow.note                 # no crying wolf

    banded = _both(_room(iso="F-18", thickness=500))[2]["Wall N"]        # mu*x ~ 10, banded
    assert banded.ci_low is not None, "expected the banded branch"
    assert banded.mu_x > eng.GEOMETRY_BIAS_MUX and banded.geometry_bias is True
    assert eng.GEOMETRY_BIAS_WARNING in banded.note

    withdrawn = _both(_room(iso="F-18", thickness=700))[2]["Wall N"]     # deep-tail branch
    assert "deep tail" in withdrawn.engine and withdrawn.ci_low is None
    assert withdrawn.geometry_bias is True
    assert eng.GEOMETRY_BIAS_WARNING in withdrawn.note

    # the text is the RSO-facing contract; it states the direction of the error and the action
    w = eng.GEOMETRY_BIAS_WARNING
    for phrase in ("μx>8", "geometry bias", "under-prediction of scatter", "Monte-Carlo"):
        assert phrase in w, phrase

    # and it must reach the document that gets signed, not just the screen
    from shieldlab.room import diagram, report_room, report_regulatory
    meta = {"facility": "T", "room_ref": "R", "licence": "-",
            "prepared_by": "-", "reviewed_by": "-"}
    d = _room(iso="F-18", thickness=250)
    d.wall("N").thickness1_mm = 500.0                    # one deep wall, three ordinary
    ae, se_ = AnalyticalEngine(d), SurrogateEngine(d)
    ar = ae.evaluate_all("check")
    sr = se_.evaluate_all("check", ar)
    rep = report_room.build_report(d, ar, "check", diagram.render(d, sr), surrogate_results=sr)
    rows = {r["barrier"]: r for r in rep["rows"]}
    assert rows["Wall N"]["geometry_bias"] is True and rows["Wall E"]["geometry_bias"] is False
    doc = report_regulatory.build_submission_html(rep, meta).decode("utf-8")
    assert "Deep-barrier caution" in doc and "Wall N" in doc.split("Deep-barrier caution")[1][:200]

    d.wall("N").thickness1_mm = 250.0                    # nothing deep -> no caution block
    ar = AnalyticalEngine(d).evaluate_all("check")
    sr = SurrogateEngine(d).evaluate_all("check", ar)
    rep = report_room.build_report(d, ar, "check", diagram.render(d, sr), surrogate_results=sr)
    assert "Deep-barrier caution" not in \
           report_regulatory.build_submission_html(rep, meta).decode("utf-8")


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
    from shieldlab.room import report_room, diagram
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

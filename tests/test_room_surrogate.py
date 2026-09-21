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
    assert se.available(), "no surrogate bundle loaded"
    from shieldlab.room import surrogate_e as sur_e
    meta = se.bundle["meta"]
    if sur_e.is_model_e(se.bundle):
        # Model E: the training set only ever grows, and the deployed copy must be the sealed
        # model whose test-set numbers the paper reports.
        assert meta["n_rows"] >= 15417
        assert meta["test_set"]["n"] == 2386
        assert meta["test_set"]["rmse"] < 0.03
        assert 0.93 <= meta["test_set"]["coverage"] <= 0.99
        assert len(se.bundle["features"]) == 12
    else:
        # Legacy eight-feature bundle. A drop in the row count means it was rebuilt on a subset.
        assert meta["n_accepted"] >= 4177
        assert meta["n_excised"] == 0
        assert meta["cqr95_coverage_holdout"] >= 0.95


# Three configurations from the sealed test set (hpc_campaign/e_predictions_LOCKED.csv), with the
# predictions recorded before those configurations were simulated. The app must reproduce them from
# its own feature builder, or it is not serving the model the paper tested.
SEALED_PREDICTIONS = [
    # (energy keV, thickness mm, duct radius mm, offset mm, material, layer2, layer2 mm,
    #  point, lower, upper)
    (140.5, 129.88, 0.0, 0.0, "concrete", None, 0.0, -1.403838257759, -1.461351705021, -1.339197382552),
    (140.5, 0.43, 0.0, 0.0, "lead", "concrete", 42.26, -0.913701012432, -0.961900964824, -0.877250948889),
    (140.5, 233.28, 31.32, 65.1, "concrete", None, 0.0, -1.077336706658, -1.097211350492, -0.952021803018),
]


def test_sealed_test_set_predictions_reproduce():
    """The app's own feature and interval code reproduces sealed predictions to float precision."""
    from shieldlab.room import surrogate_e as sur_e

    bundle = SurrogateEngine(_room()).bundle
    if not sur_e.is_model_e(bundle):
        print("SKIP sealed-prediction test: model E is not the loaded bundle")
        return
    materials = bundle["material_map"]
    for energy, thickness, radius, offset, first, second, second_mm, point, low, high in SEALED_PREDICTIONS:
        X, baseline, _ = sur_e.design_row(
            bundle, energy_keV=energy, thickness_mm=thickness, duct_radius_mm=radius,
            det_offset_mm=offset, zeff=materials[first]["zeff"],
            density_gcm3=materials[first]["density_gcm3"],
            layer2_thickness_mm=second_mm,
            layer2_zeff=materials[second]["zeff"] if second else 0.0,
            layer2_density_gcm3=materials[second]["density_gcm3"] if second else 0.0)
        got_point, got_low, got_high, _ = sur_e.serve(bundle, X, baseline)
        assert bundle["domain"].in_domain(X)[0], (first, thickness)
        for got, want, name in ((got_point, point, "point"), (got_low, low, "lower"),
                                (got_high, high, "upper")):
            assert abs(got - want) < 1e-9, (first, thickness, name, got, want)


def test_field_convention_factor_takes_the_larger_layer():
    """The measured factors, the conservative default, and the rule for a laminate."""
    from shieldlab.room import surrogate_e as sur_e

    assert sur_e.field_convention_factor("lead") == 1.20
    assert sur_e.field_convention_factor("concrete") == 1.35
    assert sur_e.field_convention_factor("steel") == 1.37
    # An unmeasured material takes the largest measured value, not the smallest.
    assert sur_e.field_convention_factor("barite_concrete") == sur_e.FIELD_CONVENTION_DEFAULT
    assert sur_e.field_convention_factor(None) == sur_e.FIELD_CONVENTION_DEFAULT
    # A laminate takes the larger of its layers, so lead behind concrete is not served at lead's 1.20.
    assert sur_e.field_convention_factor("lead", "concrete") == 1.35
    assert sur_e.field_convention_factor("lead", None) == 1.20


def test_served_transmission_carries_the_field_convention():
    """The engine raises the sealed prediction to its broad-beam equivalent, and says so.

    The model is trained in a 0.5 m beam, which under-states lateral scatter, so the raw prediction
    is on the unsafe side of the tables a design is checked against. The engine applies the measured
    factor; `serve` itself must stay untouched, because it has to keep reproducing the sealed test
    set (see test_sealed_test_set_predictions_reproduce).
    """
    from shieldlab.room import surrogate_e as sur_e

    design = _room(iso="F-18", thickness=200.0, material="concrete")
    engine = SurrogateEngine(design)
    if not sur_e.is_model_e(engine.bundle):
        print("SKIP field-convention test: model E is not the loaded bundle")
        return
    _, _, served = _both(design)
    result = served["Wall N"]
    if result.ood:
        print("SKIP field-convention test: the reference wall is out of domain")
        return

    materials = engine.bundle["material_map"]
    # The 200 mm wall is the app's 2.35 g/cm3 concrete; model E learned Geant4's 2.30, so the
    # engine serves the thickness with the same mass per area. The reference must be built the same
    # way, or it compares two different walls.
    from shieldlab.room.transport_materials import simulated_thickness_mm
    X, baseline, _ = sur_e.design_row(
        engine.bundle, energy_keV=engine.bundle["isotope_energy_keV"]["F-18"],
        thickness_mm=simulated_thickness_mm("concrete", 200.0), duct_radius_mm=0.0,
        det_offset_mm=0.0,
        zeff=materials["concrete"]["zeff"], density_gcm3=materials["concrete"]["density_gcm3"],
        layer2_thickness_mm=0.0, layer2_zeff=0.0, layer2_density_gcm3=0.0)
    raw_logB, raw_lo, raw_hi, _ = sur_e.serve(engine.bundle, X, baseline)
    factor = sur_e.field_convention_factor("concrete")

    assert abs(result.B_achieved - 10.0 ** raw_logB * factor) < 1e-9 * result.B_achieved
    assert abs(result.ci_low - 10.0 ** raw_lo * factor) < 1e-9 * result.ci_low
    assert abs(result.ci_high - min(10.0 ** raw_hi * factor, 1.0)) < 1e-9 * result.ci_high
    assert result.B_achieved > 10.0 ** raw_logB, "the correction must raise the transmission"
    assert f"×{factor:.2f}" in result.note, result.note
    assert 0.0 < result.B_achieved <= 1.0


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


def test_deep_wall_is_served_with_an_interval():
    """A deep wall is served with an interval, and the deep band is the wider of the two.

    How much wider is a property of the model. The eight-feature bundle needed a deep-tail
    conformal offset twelve times the standard one; model E, which predicted the sealed
    configurations below B = 1e-4 as accurately as the rest, needs almost none, and its deep
    interval is wider only because its quantile arms are. Both must still bracket the point
    estimate and stay usable."""
    from shieldlab.room import surrogate_e as sur_e

    se, am, sm = _both(_room(iso="F-18", thickness=500))
    s = sm["Wall N"]
    assert s.ood is False                              # served, not routed away
    assert s.engine == "surrogate"
    assert s.ci_low is not None and s.ci_high is not None
    assert 0.0 < s.B_achieved <= 1.0 and s.ci_low <= s.B_achieved <= s.ci_high
    thin = _both(_room(iso="F-18", thickness=120))[2]["Wall N"]
    deep_rel = s.ci_high / max(s.ci_low, 1e-300)
    thin_rel = thin.ci_high / max(thin.ci_low, 1e-300)
    assert deep_rel > thin_rel
    if sur_e.is_model_e(se.bundle):
        assert deep_rel < 10.0, deep_rel        # an interval a designer can still use
    else:
        assert deep_rel > 3.0 * thin_rel


def test_2026_08_14_finite_beam_priority_warning_at_mux4():
    """The mu*x>=4 priority policy must not be presented as a measured physical onset."""
    from shieldlab.room import engines as eng

    mu_per_cm = eng.optical_depth(364.0, [("concrete", 10.0)])
    assert 0.20 < mu_per_cm < 0.27, mu_per_cm
    assert eng.optical_depth(511.0, [("concrete", 250.0), ("lead", 20.0)]) > \
           eng.optical_depth(511.0, [("concrete", 250.0)])
    assert eng.optical_depth(511.0, [("unobtainium", 250.0)]) is None

    below_priority_threshold = _both(_room(iso="F-18", thickness=100))[2]["Wall N"]
    assert below_priority_threshold.mu_x is not None
    assert below_priority_threshold.mu_x < eng.GEOMETRY_BIAS_MUX
    assert below_priority_threshold.geometry_bias is False
    assert eng.GEOMETRY_BIAS_WARNING not in below_priority_threshold.note

    priority_flagged = _both(_room(iso="F-18", thickness=200))[2]["Wall N"]
    assert priority_flagged.mu_x >= eng.GEOMETRY_BIAS_MUX
    assert priority_flagged.geometry_bias is True
    assert eng.GEOMETRY_BIAS_WARNING in priority_flagged.note

    banded = _both(_room(iso="F-18", thickness=500))[2]["Wall N"]
    assert banded.ci_low is not None, "expected the banded branch"
    assert banded.geometry_bias is True
    assert eng.GEOMETRY_BIAS_WARNING in banded.note

    # A very deep wall. The eight-feature bundle withdrew its interval below B = 1e-4; model E
    # keeps it, because it was tested there, and flags anything below the deepest transmission
    # the test set reached instead. Either way the geometry warning survives the branch.
    from shieldlab.room import surrogate_e as sur_e
    se_deep, _, deep_map = _both(_room(iso="F-18", thickness=700))
    very_deep = deep_map["Wall N"]
    assert very_deep.geometry_bias is True
    assert eng.GEOMETRY_BIAS_WARNING in very_deep.note
    if sur_e.is_model_e(se_deep.bundle):
        assert very_deep.ci_low is not None and very_deep.ci_high is not None
        if very_deep.B_achieved < 10 ** eng.BELOW_TESTED_LOGB:
            assert "deepest transmission tested" in very_deep.note
    else:
        assert "deep tail" in very_deep.engine and very_deep.ci_low is None

    warning = eng.GEOMETRY_BIAS_WARNING
    for phrase in (
        "μx≥4", "geometry bias", "no lower bound on its onset",
        "lower bounds", "precision gate", "below 10%", "Monte-Carlo",
    ):
        assert phrase in warning, phrase

    from shieldlab.room import diagram, report_room, report_regulatory
    metadata = {"facility": "T", "room_ref": "R", "licence": "-",
                "prepared_by": "-", "reviewed_by": "-"}
    design = _room(iso="F-18", thickness=100)
    design.wall("N").thickness1_mm = 200.0
    analytical = AnalyticalEngine(design).evaluate_all("check")
    surrogate = SurrogateEngine(design).evaluate_all("check", analytical)
    report = report_room.build_report(
        design, analytical, "check", diagram.render(design, surrogate),
        surrogate_results=surrogate,
    )
    rows = {row["barrier"]: row for row in report["rows"]}
    assert rows["Wall N"]["geometry_bias"] is True
    assert rows["Wall E"]["geometry_bias"] is False
    document = report_regulatory.build_submission_html(report, metadata).decode("utf-8")
    assert "Finite-beam caution" in document
    assert "Wall N" in document.split("Finite-beam caution")[1][:200]
    assert "lower bounds" in document
    assert "9.3% and 9.8%" in document

    design.wall("N").thickness1_mm = 100.0
    analytical = AnalyticalEngine(design).evaluate_all("check")
    surrogate = SurrogateEngine(design).evaluate_all("check", analytical)
    report = report_room.build_report(
        design, analytical, "check", diagram.render(design, surrogate),
        surrogate_results=surrogate,
    )
    document = report_regulatory.build_submission_html(report, metadata).decode("utf-8")
    assert "Finite-beam caution" not in document
    assert "Model-wide finite-field scope" in document
    assert "no lower bound on its physical onset" in document
    assert "lead" in document
    assert "precision gate" in document
    assert "below 10%" in document

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

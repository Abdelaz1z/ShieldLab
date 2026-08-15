"""
engines.py
==========
Shielding engines that answer, per barrier path: "what gets through, does it meet
the goal, and (Design mode) how thick must this wall be?"

`AnalyticalEngine` wraps the validated `shieldlab.physics` NCRP-151/TG-108 solver
and is always available. `SurrogateEngine` (Phase B) will implement the same
`EngineResult` interface using the MC-trained Extra-Trees model with conformal
intervals and an out-of-domain guard, and is shown side-by-side.

Unit note: nuclear-medicine radionuclide sources are in mSv/week and NCRP design
goals in mGy/week; for these photon energies air kerma ~ ambient dose (1 mGy ~ 1
mSv), the same approximation the underlying ShieldLab engine uses. Results are
compared numerically on that basis and every number traces to the physics package.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..physics import sources as src
from ..physics import beams as bm
from ..physics import barriers as ba
from ..physics import solver as sv
from ..regulatory import limits as reg
from .model import RoomDesign, Wall
from .geometry import BarrierPath, all_paths

# candidate wall materials, in the order to offer them; probed for real data below
_CANDIDATE_WALL_MATERIALS = ("concrete", "lead", "steel", "barite_concrete", "brick", "gypsum")


@dataclass
class EngineResult:
    """One barrier's shielding result, from one engine."""
    barrier_id: str
    label: str
    engine: str                       # 'analytical' | 'surrogate' | 'analytical (OOD fallback)'
    B_required: Optional[float]       # transmission needed to meet goal/T
    B_achieved: Optional[float]       # transmission of the declared/suggested barrier
    dose_mSv_wk: Optional[float]      # transmitted dose at the POP
    goal_over_T: Optional[float]      # P/T threshold
    passes: Optional[bool]            # None = engine cannot evaluate (e.g. duct, analytical)
    margin: Optional[float]           # goal_over_T / dose  (>=1 pass)
    suggested_thickness_mm: Optional[float] = None   # Design mode
    material: Optional[str] = None
    ci_low: Optional[float] = None    # Phase B (CQR)
    ci_high: Optional[float] = None
    ood: bool = False
    geometry_bias: bool = False       # surrogate served a barrier deeper than mu*x = 8 (see below)
    mu_x: Optional[float] = None      # barrier optical depth, when it could be computed
    note: str = ""


def usable_wall_materials(isotope: str) -> List[str]:
    """Materials that actually have a transmission path for this isotope's gamma."""
    beam = bm.Beam(kind=bm.KIND_RADIONUCLIDE, nuclide=isotope)
    ok = []
    for m in _CANDIDATE_WALL_MATERIALS:
        try:
            b = bm.transmission_of_layer(beam, m, 100.0)
            if b is not None and 0.0 < b <= 1.0:
                ok.append(m)
        except Exception:
            continue
    return ok


class AnalyticalEngine:
    """NCRP-151/TG-108 broad-beam engine (wraps shieldlab.physics)."""

    name = "analytical"

    def __init__(self, design: RoomDesign):
        self.design = design

    # -- source & goal builders ------------------------------------------------
    def _source(self, path: BarrierPath) -> src.SourceTerm:
        s = self.design.source
        return src.radionuclide_point_source(
            nuclide=s.isotope,
            activity_mCi=s.activity_mCi(),
            d_m=path.d_pop_m,
            hours_per_week=s.source_hours_per_week(),
            occupancy=1.0,               # occupancy T is applied via the design goal, not here
        )

    def _goal(self, wall: Wall) -> reg.DesignGoal:
        adj = wall.adjacent
        area_type = "controlled" if adj.kind == "controlled" else "uncontrolled"
        return reg.design_goal(
            framework=self.design.framework,
            area_type=area_type,
            occupancy_T=adj.occupancy_T,
            override_P_weekly=adj.design_goal_P_mSv_wk,
        )

    # -- per-path evaluation ---------------------------------------------------
    def evaluate(self, path: BarrierPath, wall: Wall, mode: str) -> EngineResult:
        """mode: 'check' (evaluate declared barrier) or 'design' (suggest thickness)."""
        # A duct is a line-of-sight air channel and a maze is scatter-only: the analytical
        # broad-beam model has no geometric term for either and would mislead.
        if path.kind in ("duct", "maze"):
            what = ("Duct streaming" if path.kind == "duct" else "Maze/corner scatter")
            return EngineResult(
                barrier_id=path.label, label=path.label, engine=self.name,
                B_required=None, B_achieved=None, dose_mSv_wk=None, goal_over_T=None,
                passes=None, margin=None,
                note=f"{what} is outside the analytical model — surrogate tier used.",
            )

        source = self._source(path)
        goal = self._goal(wall)
        goal_over_T = goal.P_weekly / goal.occupancy_T if goal.occupancy_T > 0 else goal.P_weekly
        unshielded = source.total_unshielded()
        B_required = min(1.0, goal_over_T / unshielded) if unshielded > 0 else 1.0

        # material(s) for this path
        if path.kind in ("door", "window"):
            material = "lead"                      # openings entered as lead-equivalent
            layers = [(material, path.lead_equiv_mm)]
        else:
            material = wall.material1
            layers = [(wall.material1, wall.thickness1_mm)]
            if wall.material2 and wall.thickness2_mm > 0:
                layers.append((wall.material2, wall.thickness2_mm))

        if mode == "design" and path.kind == "wall":
            # suggest a single-material thickness for material1 that just meets the goal
            try:
                req_mm = sv.required_thickness(source, material, goal)
                pref_mm = sv.preferred_thickness(req_mm, material)
            except Exception as exc:
                return EngineResult(
                    barrier_id=path.label, label=path.label, engine=self.name,
                    B_required=B_required, B_achieved=None, dose_mSv_wk=None,
                    goal_over_T=goal_over_T, passes=None, margin=None,
                    material=material, note=f"No analytical data for {material}: {exc}",
                )
            barrier = ba.Barrier([ba.Layer(material, pref_mm)])
            ev = sv.evaluate(source, barrier, goal)
            return EngineResult(
                barrier_id=path.label, label=path.label, engine=self.name,
                B_required=B_required, B_achieved=ev.transmitted_total / unshielded if unshielded else None,
                dose_mSv_wk=ev.transmitted_total, goal_over_T=goal_over_T,
                passes=ev.verdict.acceptable, margin=ev.verdict.margin_ratio,
                suggested_thickness_mm=pref_mm, material=material,
                note=f"Suggested {pref_mm:g} mm {material} (required {req_mm:.1f} mm, rounded up).",
            )

        # CHECK mode (and openings in both modes): evaluate the declared barrier
        barrier = ba.Barrier([ba.Layer(m, t) for m, t in layers if t > 0])
        if not barrier.layers:
            return EngineResult(
                barrier_id=path.label, label=path.label, engine=self.name,
                B_required=B_required, B_achieved=1.0, dose_mSv_wk=unshielded,
                goal_over_T=goal_over_T, passes=(unshielded <= goal_over_T),
                margin=(goal_over_T / unshielded if unshielded > 0 else float("inf")),
                material=material, note="No barrier declared (open path).",
            )
        try:
            ev = sv.evaluate(source, barrier, goal)
        except Exception as exc:
            return EngineResult(
                barrier_id=path.label, label=path.label, engine=self.name,
                B_required=B_required, B_achieved=None, dose_mSv_wk=None,
                goal_over_T=goal_over_T, passes=None, margin=None,
                material=material, note=f"No analytical data for {material}: {exc}",
            )
        return EngineResult(
            barrier_id=path.label, label=path.label, engine=self.name,
            B_required=B_required,
            B_achieved=ev.transmitted_total / unshielded if unshielded else None,
            dose_mSv_wk=ev.transmitted_total, goal_over_T=goal_over_T,
            passes=ev.verdict.acceptable, margin=ev.verdict.margin_ratio,
            material=material,
            note=barrier.describe(),
        )

    def evaluate_all(self, mode: str) -> List[EngineResult]:
        out: List[EngineResult] = []
        wall_by_id = {w.id: w for w in self.design.walls}
        for path in all_paths(self.design):
            out.append(self.evaluate(path, wall_by_id[path.wall_id], mode))
        return out


# ===========================================================================
# Surrogate tier: the Monte-Carlo-trained Extra-Trees model (thesis, Phase B).
# ===========================================================================
import math                                   # noqa: E402  (kept local to the surrogate tier)

_BUNDLE = None
_BUNDLE_TRIED = False
_CORNER = None
_CORNER_TRIED = False

# Response-space routing floor, in log10 B. A query whose PREDICTED transmission falls below
# this is not served by the surrogate however ordinary its features look: the prospective
# validation showed the band is not calibrated there and the error is a bias, so widening the
# interval cannot fix it. Set from the measured failure boundary (B = 1e-4), not tuned.
RESPONSE_ROUTER_LOGB_MAX = -4.0

# ---------------------------------------------------------------------------
# GEOMETRY-BIAS THRESHOLD (uncorrected; disclosed, not fixed)
#
# Every training label was generated with a 0.5 m square beam footprint on the slab. That
# footprint is finite, so photons that would have scattered into the detector from wall
# material outside it were never transported. The transmission B is therefore a property of
# the barrier AND of the irradiation rig, and at depth the missing lateral scatter matters:
# the deep component of B is almost entirely build-up, and build-up is exactly what a wide
# illuminated field supplies.
#
# A dedicated convergence tier (13 GATE runs, on-axis solid concrete at the I-131 364 keV
# line, footprints 0.5 / 1.0 / 1.5 m) measured the size of it:
#
#     mu*x      B(1.5 m)/B(0.5 m)     effective build-up 0.5 m -> 1.5 m
#      8.05          x1.90                    6.14 -> 11.63
#     10.03          x1.81                    9.09 -> 16.48
#     12.01          x2.01                   10.84 -> 21.83
#
# So the training labels UNDER-state transmission by roughly a factor of two beyond
# mu*x ~ 8, and the surrogate inherits that: it under-predicts dose, which is the unsafe
# direction. The ratio is flat in mu*x over the measured range rather than growing, and the
# 1.0 -> 1.5 m step is already small (+14.4% / +6.7% / +2.5%), so 1.5 m is close to converged
# and the correct correction is not a scalar we can apply here -- it needs the corpus
# regenerated on a wider slab. Until that happens the bias is stated, not silently carried.
#
# This is NOT covered by the two guards above:
#   * the OOD guard is a feature-space test, and a deep wall is an ordinary thickness of an
#     ordinary material, so it is admitted as in-domain (all 13 extreme-tail rows in the
#     prospective validation were);
#   * the analytical fallback is not reliably the conservative option on such rows either
#     (it under-predicted dose on 2 of 12 of them, by up to 0.70 dex).
# The only honest mitigation is to tell the RSO. Hence a hard, unconditional warning.
GEOMETRY_BIAS_MUX = 8.0
GEOMETRY_BIAS_WARNING = (
    "Caution: Deep-wall transmission (μx>8) carries an uncorrected geometry bias "
    "(under-prediction of scatter). An independent Monte-Carlo check is recommended for "
    "final design sign-off."
)


def optical_depth(energy_keV: float, layers) -> Optional[float]:
    """Total optical depth mu*x of a barrier: sum over layers of (mu/rho)*rho*x, dimensionless.

    `layers` is an iterable of (material_name, thickness_mm). mu/rho is the NIST total
    attenuation coefficient interpolated log-log to `energy_keV`, and rho is the app's own
    tabulated density, so the number describes the barrier the user actually declared.
    Returns None if no layer could be evaluated (unknown material, no data), so a caller can
    distinguish "not deep" from "not known".
    """
    from .. import data_loader as dl
    from ..physics import transmission as tx
    try:
        mats = dl.load("materials")
    except Exception:
        return None
    grid, table = mats["energy_grid_MeV"], mats["materials"]
    total, seen = 0.0, False
    for material, t_mm in layers:
        m = table.get(material)
        if m is None or not t_mm or t_mm <= 0:
            continue
        try:
            mu_rho = tx.interp_mu_rho(energy_keV / 1000.0, grid, m["mu_rho"])
            rho = m["density_kg_m3"] / 1000.0          # kg/m^3 -> g/cm^3
        except Exception:
            continue
        total += mu_rho * rho * (t_mm / 10.0)          # mm -> cm
        seen = True
    return total if seen else None


def load_corner_bundle(path: Optional[str] = None):
    """Load the corner/maze surrogate bundle once (None if unavailable)."""
    global _CORNER, _CORNER_TRIED
    if _CORNER is not None or _CORNER_TRIED:
        return _CORNER
    _CORNER_TRIED = True
    try:
        import joblib
        from . import surrogate_guard as _sg
        sys.modules.setdefault("surrogate_guard", _sg)
        p = Path(path) if path else (Path(__file__).resolve().parents[2] / "models" /
                                     "corner_bundle.joblib")
        if not p.exists():
            return None
        _CORNER = joblib.load(p)
    except Exception:
        _CORNER = None
    return _CORNER


def _corner_provenance(cb) -> str:
    """Describe the corner sub-study from the bundle's own meta, for the user-facing note.

    Both figures come from the loaded bundle so they cannot disagree with the model actually
    serving the prediction. Older bundles predate the 'n' key, so it degrades to the accuracy
    alone rather than printing a wrong row count."""
    meta = (cb or {}).get("meta", {}) or {}
    n, r2 = meta.get("n"), meta.get("cv_r2")
    parts = []
    if n:
        parts.append(f"{int(n):,}-row study")
    if r2 is not None:
        parts.append(f"CV R²≈{r2}")
    return ", ".join(parts) if parts else "screening sub-study"


def load_bundle(path: Optional[str] = None):
    """Load the deployed surrogate bundle once (or return None if unavailable, so the
    app degrades gracefully to analytical-only). Aliases the guard module into sys.modules
    under the name the pickle expects ('surrogate_guard')."""
    global _BUNDLE, _BUNDLE_TRIED
    if _BUNDLE is not None or _BUNDLE_TRIED:
        return _BUNDLE
    _BUNDLE_TRIED = True
    try:
        import joblib
        from . import surrogate_guard as _sg
        sys.modules.setdefault("surrogate_guard", _sg)   # pickle refers to surrogate_guard.*
        p = Path(path) if path else (Path(__file__).resolve().parents[2] / "models" /
                                     "surrogate_bundle.joblib")
        if not p.exists():
            return None
        _BUNDLE = joblib.load(p)
    except Exception:
        _BUNDLE = None
    return _BUNDLE


class SurrogateEngine:
    """Geometry-aware MC surrogate: predicts broad-beam B with a 95% CI and an OOD guard.
    Reuses AnalyticalEngine for the source/goal/unshielded terms so the two tiers are
    directly comparable. Falls back to the analytical value for out-of-domain queries."""

    name = "surrogate"

    def __init__(self, design: RoomDesign, bundle_path: Optional[str] = None):
        self.design = design
        self.analytical = AnalyticalEngine(design)
        self.bundle = load_bundle(bundle_path)

    def available(self) -> bool:
        return self.bundle is not None

    def _features(self, path: BarrierPath, wall: Wall, thickness_mm: float):
        import numpy as np
        b = self.bundle
        e = b["isotope_energy_keV"].get(self.design.source.isotope)
        mat = "lead" if path.kind in ("door", "window") else wall.material1
        mm = b["material_map"]
        if e is None or mat not in mm:
            return None
        z, rho = mm[mat]["zeff"], mm[mat]["density_gcm3"]
        l2t, l2z = 0.0, 0.0
        if path.kind == "wall" and wall.material2 and wall.thickness2_mm > 0 and wall.material2 in mm:
            l2t, l2z = wall.thickness2_mm, mm[wall.material2]["zeff"]
        # feature order MUST match bundle["features"]
        return np.array([[e, thickness_mm, path.duct_radius_mm, path.offset_m * 1000.0,
                          z, rho, l2t, l2z]], dtype=float)

    def _barrier_mu_x(self, path: BarrierPath, wall: Wall,
                      thickness_mm: float) -> Optional[float]:
        """Optical depth of the barrier this prediction is about. Layer list mirrors
        `_features` exactly, so the mu*x reported is the mu*x of the thing the model was
        asked about (the suggested wall in design mode, the declared one in check mode)."""
        e = (self.bundle or {}).get("isotope_energy_keV", {}).get(self.design.source.isotope)
        if e is None:
            return None
        if path.kind in ("door", "window"):
            layers = [("lead", thickness_mm)]
        else:
            layers = [(wall.material1, thickness_mm)]
            if wall.material2 and wall.thickness2_mm > 0:
                layers.append((wall.material2, wall.thickness2_mm))
        return optical_depth(e, layers)

    def _evaluate_maze(self, path: BarrierPath, wall: Wall) -> EngineResult:
        """Corner/maze scatter via the dedicated corner surrogate (screening tier: honest,
        wide conformal band; strict guard; no analytical fallback exists).

        The sub-study's size and accuracy are read from the bundle's own meta block, never
        hardcoded here: this note is user-facing provenance, and a literal row count silently
        went stale across two retrains (105 -> 214 -> 741) while the R^2 beside it was read
        live, so the app displayed a self-contradictory pair."""
        import numpy as np
        cb = load_corner_bundle()
        source = self.analytical._source(path)
        goal = self.analytical._goal(wall)
        gT = goal.P_weekly / goal.occupancy_T if goal.occupancy_T > 0 else goal.P_weekly
        unshielded = source.total_unshielded()
        mm = self.bundle["material_map"] if self.bundle else {}
        e = (self.bundle or {}).get("isotope_energy_keV", {}).get(self.design.source.isotope)
        if cb is None or e is None or wall.material1 not in mm or path.ret_material not in mm:
            return EngineResult(barrier_id=path.label, label=path.label, engine="OOD — needs MC",
                                B_required=None, B_achieved=None, dose_mSv_wk=None, goal_over_T=gT,
                                passes=None, margin=None, ood=True,
                                note="Corner surrogate unavailable for these materials — full MC needed.")
        z1, r1 = mm[wall.material1]["zeff"], mm[wall.material1]["density_gcm3"]
        z2, r2 = mm[path.ret_material]["zeff"], mm[path.ret_material]["density_gcm3"]
        X = np.array([[e, wall.thickness1_mm, z1, r1,
                       path.ret_thickness_mm, z2, r2,
                       path.corridor_m * 1000.0, path.shadow_offset_m * 1000.0]], dtype=float)
        if not cb["domain"].in_domain(X)[0]:
            return EngineResult(barrier_id=path.label, label=path.label, engine="OOD — needs MC",
                                B_required=None, B_achieved=None, dose_mSv_wk=None, goal_over_T=gT,
                                passes=None, margin=None, ood=True,
                                note="Outside the corner sub-study's trusted domain "
                                     "(corridor 0.2–1.5 m, offset 0.3–0.7 m) — full MC needed.")
        logB = float(cb["model"].predict(X)[0])
        Q = cb["Q95_log10"]
        B = min(10.0 ** logB, 1.0)
        B_lo, B_hi = 10.0 ** (logB - Q), min(10.0 ** (logB + Q), 1.0)
        dose = unshielded * B
        return EngineResult(
            barrier_id=path.label, label=path.label, engine="corner surrogate",
            B_required=(min(1.0, gT / unshielded) if unshielded > 0 else 1.0),
            B_achieved=B, dose_mSv_wk=dose, goal_over_T=gT,
            passes=(dose <= gT), margin=(gT / dose if dose > 0 else None),
            material=wall.material1, ci_low=B_lo, ci_high=B_hi, ood=False,
            note=(f"Corner/maze SCREENING estimate ({_corner_provenance(cb)}); "
                  f"95% band [{B_lo:.1e}, {B_hi:.1e}] is wide by design — confirm the final "
                  f"maze with a full MC run."))

    def evaluate(self, path: BarrierPath, wall: Wall, thickness_mm: float,
                 analytical: Optional[EngineResult] = None) -> Optional[EngineResult]:
        if not self.available():
            return None
        if path.kind == "maze":
            return self._evaluate_maze(path, wall)
        b = self.bundle
        X = self._features(path, wall, thickness_mm)
        source = self.analytical._source(path)
        goal = self.analytical._goal(wall)
        gT = goal.P_weekly / goal.occupancy_T if goal.occupancy_T > 0 else goal.P_weekly
        unshielded = source.total_unshielded()

        if X is None:
            return EngineResult(barrier_id=path.label, label=path.label, engine=self.name,
                                B_required=None, B_achieved=None, dose_mSv_wk=None, goal_over_T=gT,
                                passes=None, margin=None, note="No surrogate features for this path.")

        # OOD guard: feature box + kNN density + excised-region proximity
        dom, exc = b["domain"], b["excised"]
        ood = (not dom.in_domain(X)[0]) or bool(exc.near_excised(X)[0])
        if ood:
            # defer to the conservative analytical value (if the analytical tier has one)
            aB = analytical.B_achieved if analytical else None
            aDose = analytical.dose_mSv_wk if analytical else None
            aPass = analytical.passes if analytical else None
            if aB is not None:
                note = ("Outside the surrogate's trusted domain (deep penetration / off-axis "
                        "beam-shadow); conservative analytical value used.")
                eng = "analytical (OOD fallback)"
            else:
                note = ("Outside the surrogate's trusted domain AND unmodellable analytically "
                        "(off-axis duct streaming) — a full Monte-Carlo simulation is required "
                        "(HPC campaign).")
                eng = "OOD — needs MC"
            return EngineResult(
                barrier_id=path.label, label=path.label,
                engine=eng, B_required=None, B_achieved=aB,
                dose_mSv_wk=aDose, goal_over_T=gT, passes=aPass,
                margin=(gT / aDose if aDose else None), material=wall.material1, ood=True,
                note=note)

        # in-domain surrogate prediction + group-conditional (Mondrian, 3-group) CQR 95% interval:
        # the two HPC-rescued regions (deep tail; deep off-axis beam-shadow corner), where the
        # surrogate is weaker, each get their own wider conformal offset. Group taxonomy uses the
        # query's offset + the model's own prediction (available at inference; deep > shadow
        # precedence). Keys are absent in pre-rescue bundles -> global band (backward compatible).
        logB = float(b["model"].predict(X)[0])

        # Geometry bias is a property of the BARRIER, not of the prediction, so it is
        # evaluated once here and carried by whichever branch below serves the answer.
        mu_x = self._barrier_mu_x(path, wall, thickness_mm)
        deep_wall = mu_x is not None and mu_x > GEOMETRY_BIAS_MUX
        gb_note = f"  ⚠ μx≈{mu_x:.1f}. {GEOMETRY_BIAS_WARNING}" if deep_wall else ""

        # ---- DEEP-TAIL INTERVAL FLAG (deployment mitigation; NOT part of the sealed
        # pre-registration, and deliberately NOT a substitution).
        #
        # The OOD guard above is a FEATURE-space test: it detects a query unlike the training
        # inputs. It cannot detect a query whose true OUTPUT lies below the region the training
        # labels constrain, because such a query is an ordinary thickness of an ordinary
        # material. The prospective validation measured the consequence: of the 13 sealed
        # in-domain rows with true B < 1e-4, the band covered the truth in 5 (38.5%,
        # Wilson [17.7%, 64.5%]).
        #
        # The obvious mitigation is to substitute the analytical value here. It was implemented,
        # measured against the sealed rows, and REJECTED, because the measurement says it makes
        # those queries less safe rather than more:
        #
        #   surrogate on those rows : conservative (over-predicts dose) 13/13 = 100%
        #                             Wilson [77%, 100%], mean +0.67 dex, min +0.36
        #   analytical on those rows: conservative 10/12 = 83%, Wilson [55%, 95%],
        #                             min -0.70 dex  <- under-predicts dose, the unsafe direction
        #
        # The surrogate's deep-tail error is a COVERAGE failure, not a safety failure: the
        # point estimate is unfailingly conservative, the interval around it is not calibrated.
        # Replacing a wrong-but-conservative number with one that under-predicts dose on ~1 row
        # in 6 would trade a reporting defect for a shielding defect. So the point estimate is
        # kept, the interval is withdrawn rather than shown with false authority, and the result
        # is flagged for an independent Monte-Carlo check. ----
        if logB < RESPONSE_ROUTER_LOGB_MAX:
            B = 10.0 ** logB
            dose = unshielded * B
            return EngineResult(
                barrier_id=path.label, label=path.label,
                engine="surrogate (deep tail: interval withdrawn)",
                B_required=(min(1.0, gT / unshielded) if unshielded > 0 else 1.0),
                B_achieved=B, dose_mSv_wk=dose, goal_over_T=gT,
                passes=(dose <= gT), margin=(gT / dose if dose > 0 else None),
                material=wall.material1, ci_low=None, ci_high=None, ood=True,
                geometry_bias=deep_wall, mu_x=mu_x,
                note=(gb_note.strip() + ("  " if gb_note else "") +
                      f"Predicted B={B:.2e} is below B=1e{RESPONSE_ROUTER_LOGB_MAX:.0f}, where "
                      f"prospective validation measured the 95% interval to be NOT calibrated "
                      f"(38.5% coverage, Wilson [17.7%, 64.5%]). No interval is reported here. "
                      f"The point estimate is retained because it was conservative on every "
                      f"such row tested (13/13, mean +0.67 dex); the analytical value was NOT "
                      f"substituted because it under-predicted dose on 2 of 12 of them. "
                      f"Confirm this barrier with an independent Monte-Carlo run."))

        cq = b["cqr"]
        off_idx = b["features"].index("det_offset_mm")
        deep = logB < cq.get("deep_logB_max", -float("inf"))
        shadow = (not deep
                  and float(X[0, off_idx]) > cq.get("shadow_offset_mm", float("inf"))
                  and logB < cq.get("shadow_logB_max", -float("inf")))
        Q = (cq.get("Q95_deep", cq["Q95"]) if deep
             else cq.get("Q95_shadow", cq["Q95"]) if shadow
             else cq["Q95"])
        lo = float(cq["q_lo"].predict(X)[0]) - Q
        hi = float(cq["q_hi"].predict(X)[0]) + Q
        B = 10.0 ** logB
        B_lo, B_hi = 10.0 ** lo, 10.0 ** hi
        dose = unshielded * B
        # verdict/margin on the point estimate (consistent with the analytical tier); the 95%
        # CI is reported alongside so the RSO sees the uncertainty and can design on the
        # conservative bound or the analytical value as policy requires.
        passes = dose <= gT
        margin_hi = gT / (unshielded * B_hi) if unshielded * B_hi > 0 else None   # conservative margin
        band_note = (" (deep tail: wide band)" if deep
                     else " (deep off-axis: wide band)" if shadow else "")
        return EngineResult(
            barrier_id=path.label, label=path.label, engine=self.name,
            B_required=(min(1.0, gT / unshielded) if unshielded > 0 else 1.0),
            B_achieved=B, dose_mSv_wk=dose, goal_over_T=gT,
            passes=passes, margin=(gT / dose if dose > 0 else None),
            material=wall.material1, ci_low=B_lo, ci_high=B_hi,
            geometry_bias=deep_wall, mu_x=mu_x,
            note=((f"MC surrogate B={B:.2e}, 95% CI [{B_lo:.1e}, {B_hi:.1e}]{band_note}; "
                   f"conservative (upper-bound) margin ×{margin_hi:.2f}."
                   if margin_hi is not None else
                   f"MC surrogate B={B:.2e}, 95% CI [{B_lo:.1e}, {B_hi:.1e}]{band_note}.")
                  + gb_note))

    def evaluate_all(self, mode: str,
                     analytical_results: Optional[List[EngineResult]] = None) -> List[EngineResult]:
        """Evaluate every path with the surrogate. Thickness per path = the analytical
        suggestion (design mode) or the declared build (check mode)."""
        ar = {r.label: r for r in (analytical_results or [])}
        out: List[EngineResult] = []
        wall_by_id = {w.id: w for w in self.design.walls}
        for path in all_paths(self.design):
            wall = wall_by_id[path.wall_id]
            a = ar.get(path.label)
            if path.kind in ("door", "window"):
                thickness = path.lead_equiv_mm
            elif mode == "design" and a is not None and a.suggested_thickness_mm is not None:
                thickness = a.suggested_thickness_mm      # evaluate the suggested wall
            else:
                thickness = wall.thickness1_mm
            out.append(self.evaluate(path, wall, thickness, analytical=a))
        return out

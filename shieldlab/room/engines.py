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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List, Optional

from ..physics import sources as src
from ..physics import beams as bm
from ..physics import barriers as ba
from ..physics import solver as sv
from ..regulatory import limits as reg
from .model import RoomDesign, Wall
from .geometry import BarrierPath, all_paths
from .transport_materials import served_as_note, simulated_thickness_mm

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
    geometry_bias: bool = False       # finite-field warning at measured optical depth (see below)
    mu_x: Optional[float] = None      # barrier optical depth, when it could be computed
    note: str = ""


@dataclass(frozen=True)
class _Served:
    """Model E's broad-beam answer for one barrier, in log10 B: for one line, or summed over the
    source's lines, in which case `factor`, `group` and `energy_keV` are those of the line carrying
    most of the transmitted dose and `mu_x` is the deepest line's (see `_sum_lines`)."""
    energy_keV: float
    logB: float
    lo: float
    hi: float
    group: str
    inside: bool
    mu_x: Optional[float]
    factor: tuple                      # surrogate_e.FieldFactor
    substituted: tuple = ()            # lines bounded by a harder line (see `_sum_lines`)


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

# Response-space routing floor, in log10 B, for the LEGACY eight-feature bundle only. A query whose
# predicted transmission fell below this was served without an interval however ordinary its
# features looked, because that model's band was measured as not calibrated there and its error was
# a bias. Model E removed the cause: on the sealed test set it predicted the 182 configurations
# below B = 1e-4 with the same accuracy as the rest (0.023 in log10 B) and its interval covered
# 98.4% of them, so no withdrawal applies to it.
RESPONSE_ROUTER_LOGB_MAX = -4.0

# Model E's test set reached B = 1.1e-5. Below that the model still answers, but no coverage has
# been measured, so the result carries a note instead of a silent extrapolation.
BELOW_TESTED_LOGB = -5.0

# ---------------------------------------------------------------------------
# GEOMETRY-BIAS THRESHOLD (corrected by measured factors; the residual is disclosed)
#
# Every training label used a finite 0.5 m square beam, which truncates lateral scatter. Model E's
# served transmission is raised by the broad-beam factor Conventions 3 and 4 measured for its
# material and depth with the beam widened to 3.5 m (`surrogate_e.field_convention`): concrete
# 1.72-2.07x, rising with depth; steel 1.57x; lead 1.11x, served as 1.20x. A fixed 0.5 m beam
# changed only 0.47% when the slab widened from 2 to 3 m, so this is beam truncation, not slab
# truncation.
#
# The flag stays because of what is still uncertain. Concrete at mu*x 4 is a lower bound: its last
# step, 2.5 -> 3.5 m, still rose 0.7%. Only 364 and 511 keV were measured, and materials other
# than lead and steel borrow the concrete factor. The deficit was already 1.72x at mu*x 4, the
# shallowest depth measured, so the mu*x>=4 flag is a priority rule, not an onset claim.
#
# This is NOT covered by the two guards above:
#   * the OOD guard is a feature-space test, and a deep wall is an ordinary thickness of an
#     ordinary material, so it is admitted as in-domain (all 13 extreme-tail rows in the
#     prospective validation were);
#   * the analytical fallback is not reliably the conservative option on such rows either
#     (it under-predicted dose on 2 of 12 of them, by up to 0.70 dex).
# Hence a hard, unconditional warning to the RSO on the residual.
GEOMETRY_BIAS_MUX = 4.0
GEOMETRY_BIAS_WARNING = (
    "Caution: finite-beam correction (μx≥4). The Monte-Carlo surrogate was trained in a 0.5 m "
    "beam, which under-states scatter, so its transmission has been raised by the broad-beam "
    "factor measured for this material and depth with the beam widened to 3.5 m: concrete "
    "1.72× at μx 4 rising to 2.07× at μx 8, steel 1.57×, lead 1.11× (served as 1.20×). "
    "Concrete at μx 4 is a lower bound, because its widest step was still rising by 0.7%; "
    "that step is added to the upper limit. Only 364 and 511 keV were measured, and other "
    "materials take the concrete factor. The "
    "deficit was already 1.72× at the shallowest depth measured, so the μx≥4 flag marks "
    "priority, not the onset. An independent Monte-Carlo check with reviewed irradiation "
    "geometry is required for final design sign-off."
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
    under the name the pickle expects ('surrogate_guard').

    Model E is preferred when its bundle is present, and the eight-feature bundle is the
    fallback, so a deploy without the larger file still serves predictions."""
    global _BUNDLE, _BUNDLE_TRIED
    if _BUNDLE is not None or _BUNDLE_TRIED:
        return _BUNDLE
    _BUNDLE_TRIED = True
    try:
        import joblib
        from . import surrogate_guard as _sg
        sys.modules.setdefault("surrogate_guard", _sg)   # pickle refers to surrogate_guard.*
        models = Path(__file__).resolve().parents[2] / "models"
        candidates = ([Path(path)] if path else
                      [models / "surrogate_bundle_e.joblib", models / "surrogate_bundle.joblib"])
        p = next((c for c in candidates if c.exists()), None)
        if p is None:
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
        served = simulated_thickness_mm(mat, thickness_mm)
        if served is None:
            return None
        z, rho = mm[mat]["zeff"], mm[mat]["density_gcm3"]
        l2t, l2z = 0.0, 0.0
        if path.kind == "wall" and wall.material2 and wall.thickness2_mm > 0 and wall.material2 in mm:
            l2t = simulated_thickness_mm(wall.material2, wall.thickness2_mm)
            if l2t is None:
                return None
            l2z = mm[wall.material2]["zeff"]
        # feature order MUST match bundle["features"]
        return np.array([[e, served, path.duct_radius_mm, path.offset_m * 1000.0,
                          z, rho, l2t, l2z]], dtype=float)

    def _barrier_mu_x(self, path: BarrierPath, wall: Wall, thickness_mm: float,
                      energy_keV: Optional[float] = None) -> Optional[float]:
        """Optical depth of the barrier this prediction is about, at `energy_keV` or the source's
        principal line. Layer list mirrors `_features` exactly, so the mu*x reported is the mu*x of
        the thing the model was asked about (the suggested wall in design mode, the declared one in
        check mode)."""
        e = energy_keV if energy_keV is not None else self._principal_energy()
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
        primary = simulated_thickness_mm(wall.material1, wall.thickness1_mm)
        returned = simulated_thickness_mm(path.ret_material, path.ret_thickness_mm)
        if primary is None or returned is None:
            return EngineResult(barrier_id=path.label, label=path.label, engine="OOD — needs MC",
                                B_required=None, B_achieved=None, dose_mSv_wk=None, goal_over_T=gT,
                                passes=None, margin=None, ood=True,
                                note="This product's density differs from the simulated material's "
                                     "in a way equal mass per area cannot correct — full MC needed.")
        z1, r1 = mm[wall.material1]["zeff"], mm[wall.material1]["density_gcm3"]
        z2, r2 = mm[path.ret_material]["zeff"], mm[path.ret_material]["density_gcm3"]
        X = np.array([[e, primary, z1, r1,
                       returned, z2, r2,
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

    def _model_e_materials(self, path: BarrierPath, wall: Wall):
        """The layers model E sees for this path: the first material, and the second where it applies.

        A door or window is served as its lead equivalent, so its first layer is lead whatever the
        wall is made of, and it has no second layer.
        """
        first = "lead" if path.kind in ("door", "window") else wall.material1
        second = (wall.material2 if path.kind == "wall" and wall.material2
                  and wall.thickness2_mm > 0 else None)
        return first, second

    def _lines(self):
        """(energy keV, air-kerma weight) of each line model E serves for the source, the principal
        line first. A nuclide with no line table is served at the bundle's one line."""
        from . import surrogate_e as se
        isotope = self.design.source.isotope
        domain = self.bundle["domain"]
        column = domain.features.index("primary_energy_keV")
        lines = se.kerma_weighted_lines(isotope, float(domain.lo[column]), float(domain.hi[column]))
        if lines is None:
            energy = self.bundle["isotope_energy_keV"].get(isotope)
            return [] if energy is None else [(energy, 1.0)]
        return sorted(lines, key=lambda line: -line[1])

    def _principal_energy(self) -> Optional[float]:
        if not self.bundle:
            return None
        lines = self._lines()
        return lines[0][0] if lines else None

    def _model_e_row(self, path: BarrierPath, wall: Wall, thickness_mm: float,
                     energy_keV: Optional[float] = None):
        """Feature row and baseline for model E at `energy_keV` or the source's principal line, or
        None when a material or line is unknown."""
        from . import surrogate_e as se
        b = self.bundle
        energy = energy_keV if energy_keV is not None else self._principal_energy()
        materials = b["material_map"]
        first, second = self._model_e_materials(path, wall)
        if energy is None or first not in materials:
            return None
        use_second = second is not None and second in materials
        served_first = simulated_thickness_mm(first, thickness_mm)
        served_second = simulated_thickness_mm(second, wall.thickness2_mm) if use_second else 0.0
        if served_first is None or served_second is None:
            return None
        try:
            return se.design_row(
                b, energy_keV=energy, thickness_mm=served_first,
                duct_radius_mm=path.duct_radius_mm, det_offset_mm=path.offset_m * 1000.0,
                zeff=materials[first]["zeff"], density_gcm3=materials[first]["density_gcm3"],
                layer2_thickness_mm=served_second,
                layer2_zeff=materials[second]["zeff"] if use_second else 0.0,
                layer2_density_gcm3=materials[second]["density_gcm3"] if use_second else 0.0)
        except ValueError:
            return None            # e.g. a duct wider than the geometry the model was trained on

    def _serve_spectrum(self, path: BarrierPath, wall: Wall,
                        thicknesses: List[float]) -> List[Optional[_Served]]:
        """Model E's broad-beam answer at each thickness, summed over the source's lines.

        Every (thickness, line) row is served in one batch. Each line is raised by the broad-beam
        factor for its own depth, then the lines are summed with their air-kerma weights. None where
        the principal line cannot be built at all.
        """
        import numpy as np
        from . import surrogate_e as se
        lines = self._lines()
        rows, where = [], {}
        for i, thickness in enumerate(thicknesses):
            for j, (energy, _) in enumerate(lines):
                built = self._model_e_row(path, wall, thickness, energy)
                if built is not None:
                    where[i, j] = len(rows)
                    rows.append(built)
        if not rows:
            return [None] * len(thicknesses)
        X = np.vstack([row for row, _, _ in rows])
        inside = self.bundle["domain"].in_domain(X)
        point, lo, hi, groups = se.serve_batch(self.bundle, X,
                                               np.array([baseline for _, baseline, _ in rows]))
        materials = self._model_e_materials(path, wall)
        answers = {}
        for (i, j), k in where.items():
            energy = lines[j][0]
            mu_x = self._barrier_mu_x(path, wall, thicknesses[i], energy)
            if mu_x is None:                   # barite concrete has no mu/rho table in the app;
                mu_x = float(rows[k][2])       # the model's own depth stands in
            factor = se.field_convention(mu_x, *materials)
            broad = se.apply_field_convention(factor, point[k], lo[k], hi[k])
            answers[i, j] = _Served(energy, *broad, groups[k], bool(inside[k]), mu_x, factor)
        return [_sum_lines(lines, [answers.get((i, j)) for j in range(len(lines))])
                for i in range(len(thicknesses))]

    def _evaluate_model_e(self, path: BarrierPath, wall: Wall, thickness_mm: float,
                          analytical: Optional[EngineResult], gT: float,
                          unshielded: float) -> EngineResult:
        """Serve model E: point estimate, 95% interval, guard, and the standing beam caveat."""
        b = self.bundle
        served = self._serve_spectrum(path, wall, [thickness_mm])[0]
        if served is None:
            return EngineResult(barrier_id=path.label, label=path.label, engine=self.name,
                                B_required=None, B_achieved=None, dose_mSv_wk=None, goal_over_T=gT,
                                passes=None, margin=None, note="No surrogate features for this path.")
        if not served.inside:
            aB = analytical.B_achieved if analytical else None
            aDose = analytical.dose_mSv_wk if analytical else None
            if aB is not None:
                note = ("Outside the surrogate's trusted domain; the analytical value is used. "
                        "An independent Monte-Carlo run is the safer check.")
                engine = "analytical (OOD fallback)"
            else:
                note = ("Outside the surrogate's trusted domain AND unmodellable analytically "
                        "(off-axis duct streaming) — a full Monte-Carlo simulation is required.")
                engine = "OOD — needs MC"
            return EngineResult(
                barrier_id=path.label, label=path.label, engine=engine, B_required=None,
                B_achieved=aB, dose_mSv_wk=aDose, goal_over_T=gT,
                passes=(analytical.passes if analytical else None),
                margin=(gT / aDose if aDose else None), material=wall.material1, ood=True, note=note)

        # The model is trained in a 0.5 m beam and the standards tabulate a broad one, so each line
        # was raised to its broad-beam equivalent before the lines were summed. `serve` is left
        # untouched, so it still reproduces the paper's sealed predictions.
        logB, lo, hi, group = served.logB, served.lo, served.hi, served.group
        mu_x, factor = served.mu_x, served.factor
        finite_beam_bias = mu_x is not None and mu_x >= GEOMETRY_BIAS_MUX
        gb_note = f"  ⚠ μx≈{mu_x:.1f}. {GEOMETRY_BIAS_WARNING}" if finite_beam_bias else ""
        B, B_lo, B_hi = 10.0 ** logB, 10.0 ** lo, min(10.0 ** hi, 1.0)
        dose = unshielded * B
        margin_hi = gT / (unshielded * B_hi) if unshielded * B_hi > 0 else None
        band_note = {"deep_tail": " (deep tail)", "beam_shadow": " (deep off-axis)"}.get(group, "")
        interval = "95% CI" if len(self._lines()) < 2 else "interval (summed line edges)"
        below_tested = (" The prediction is below the deepest transmission tested (about 1e-5), "
                        "where the interval has no measured coverage; confirm with Monte Carlo."
                        if logB < BELOW_TESTED_LOGB else "")
        first, second = self._model_e_materials(path, wall)
        omitted = second is not None and second not in b["material_map"]
        layers = [(first, thickness_mm)] + ([(second, wall.thickness2_mm)] if second
                                            and not omitted else [])
        density_note = served_as_note(layers)
        if omitted:
            density_note += (f" The second layer ({second}) is not among the surrogate's training "
                             f"materials and is left out, which over-states the transmission "
                             f"(the conservative direction).")
        return EngineResult(
            barrier_id=path.label, label=path.label, engine=self.name,
            B_required=(min(1.0, gT / unshielded) if unshielded > 0 else 1.0),
            B_achieved=B, dose_mSv_wk=dose, goal_over_T=gT,
            passes=(dose <= gT), margin=(gT / dose if dose > 0 else None),
            material=wall.material1, ci_low=B_lo, ci_high=B_hi,
            geometry_bias=finite_beam_bias, mu_x=mu_x,
            note=((f"MC surrogate B={B:.2e}, {interval} [{B_lo:.1e}, {B_hi:.1e}]{band_note}; "
                   f"conservative (upper-bound) margin ×{margin_hi:.2f}."
                   if margin_hi is not None else
                   f"MC surrogate B={B:.2e}, {interval} [{B_lo:.1e}, {B_hi:.1e}]{band_note}.")
                  + f" Includes the ×{factor.value:.2f} broad-beam factor measured for this "
                    f"material and depth; its own 95% range (×{factor.low:.2f}–{factor.high:.2f}) "
                    f"is carried into the interval."
                  + self._spectrum_note(served) + density_note + below_tested + gb_note))

    def _spectrum_note(self, served: _Served) -> str:
        """How the source's lines were served, for a nuclide served over more than one line."""
        lines = self._lines()
        if len(lines) < 2:
            return ""
        listed = ", ".join(f"{energy:g} keV ({weight:.0%})" for energy, weight in lines)
        note = (f" Served over {self.design.source.isotope}'s lines, weighted by unshielded air "
                f"kerma: {listed}; each line takes the factor for its own depth, and the factor "
                f"quoted is that of the {served.energy_keV:g} keV line, the directly served line "
                f"carrying most of the transmitted dose. The interval sums each line's calibrated "
                f"95% edges. That is a 95% interval if the lines' errors move together and wider if "
                f"they are near normal, but it has not been calibrated against full-spectrum Monte "
                f"Carlo; its distribution-free floor is {1 - 0.05 * len(lines):.0%}. Lines below "
                f"100 keV are left out, which over-states the transmission.")
        if served.substituted:
            bounded = ", ".join(f"{energy:g}" for energy in served.substituted)
            note += (f" The {bounded} keV line is outside the trained domain at this depth and is "
                     f"bounded by the next harder line, which transmits more.")
        return note

    def _goal_and_unshielded(self, path: BarrierPath, wall: Wall):
        """The path's dose limit P/T and its unshielded weekly dose, both in mSv/week."""
        goal = self.analytical._goal(wall)
        gT = goal.P_weekly / goal.occupancy_T if goal.occupancy_T > 0 else goal.P_weekly
        return gT, self.analytical._source(path).total_unshielded()

    def _thickness_candidates(self, path: BarrierPath, wall: Wall) -> List[float]:
        """Standard thicknesses of the wall's first material, thinnest first, up to the thickest
        and, at the principal line, the deepest barrier the trained domain holds."""
        domain = self.bundle["domain"]
        thickest = float(domain.hi[domain.features.index("thickness_mm")])
        deepest = float(domain.hi[domain.features.index("nmfp_total")])
        step = sv.thickness_increment(wall.material1)
        candidates = []
        for count in range(1, 100_000):
            thickness = count * step
            served = simulated_thickness_mm(wall.material1, thickness)
            built = self._model_e_row(path, wall, thickness)
            if served is None or served > thickest or built is None or built[2] > deepest:
                break
            candidates.append(thickness)
        return candidates

    def _size_wall_model_e(self, path: BarrierPath, wall: Wall, gT: float,
                           unshielded: float) -> Optional[float]:
        """Thinnest standard thickness of the wall's first material whose served 95% upper limit
        meets the goal, or None when no thickness inside the trained domain does.

        A thickness is accepted only if every thicker candidate meets the goal too, served inside
        the domain: a tree ensemble is piecewise constant in thickness, and a thin candidate that
        passes on one step of the model must not be offered ahead of a thicker one that fails or
        that the model cannot vouch for. Only candidates beyond the thick end of the domain are
        passed over.
        """
        candidates = self._thickness_candidates(path, wall)
        if not candidates or gT <= 0:
            return None
        limit = math.log10(gT / unshielded)
        sized = None
        reached_domain = False
        for thickness, served in reversed(list(zip(candidates,
                                                   self._serve_spectrum(path, wall, candidates)))):
            if served is None or not served.inside:
                if reached_domain:
                    break
                continue
            reached_domain = True
            if served.hi > limit:
                break
            sized = thickness
        return sized

    def _design_wall(self, path: BarrierPath, wall: Wall,
                     analytical: Optional[EngineResult]) -> EngineResult:
        """Design mode for a solid wall: size it from the surrogate's own 95% upper limit.

        When no thickness inside the trained domain meets the goal, the analytical suggestion (or,
        without one, the declared thickness) is evaluated instead, and the note says so. A wall the
        surrogate cannot model at all, and one that needs no shielding, are evaluated as before.
        """
        gT, unshielded = self._goal_and_unshielded(path, wall)
        analytical_mm = analytical.suggested_thickness_mm if analytical else None
        fallback_mm = analytical_mm if analytical_mm is not None else wall.thickness1_mm
        modelled = self._model_e_row(path, wall, sv.thickness_increment(wall.material1)) is not None
        sized = (self._size_wall_model_e(path, wall, gT, unshielded)
                 if modelled and unshielded > gT else None)
        if sized is None:
            result = self.evaluate(path, wall, fallback_mm, analytical=analytical)
            if not modelled or unshielded <= gT:
                return result
            which = ("the analytical suggestion" if analytical_mm is not None
                     else "the declared thickness")
            reason = ("A design goal of zero cannot be met by any finite barrier" if gT <= 0
                      else "The surrogate found no thickness inside its trained domain whose 95% "
                           "upper limit meets the goal")
            return replace(result, note=f"{reason}; {which} is evaluated instead. " + result.note)
        result = self._evaluate_model_e(path, wall, sized, analytical, gT, unshielded)
        compared = (f" (the analytical method suggests {analytical_mm:g} mm)"
                    if analytical_mm is not None else "")
        return replace(result, suggested_thickness_mm=sized,
                       note=(f"Sized by the surrogate: {sized:g} mm {wall.material1} is the thinnest "
                             f"standard thickness whose 95% upper limit meets the goal{compared}. "
                             + result.note))

    def evaluate(self, path: BarrierPath, wall: Wall, thickness_mm: float,
                 analytical: Optional[EngineResult] = None) -> Optional[EngineResult]:
        if not self.available():
            return None
        if path.kind == "maze":
            return self._evaluate_maze(path, wall)
        b = self.bundle
        from . import surrogate_e as se
        if se.is_model_e(b):
            gT, unshielded = self._goal_and_unshielded(path, wall)
            return self._evaluate_model_e(path, wall, thickness_mm, analytical, gT, unshielded)
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
        finite_beam_bias = mu_x is not None and mu_x >= GEOMETRY_BIAS_MUX
        gb_note = f"  ⚠ μx≈{mu_x:.1f}. {GEOMETRY_BIAS_WARNING}" if finite_beam_bias else ""

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
                geometry_bias=finite_beam_bias, mu_x=mu_x,
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
            geometry_bias=finite_beam_bias, mu_x=mu_x,
            note=((f"MC surrogate B={B:.2e}, 95% CI [{B_lo:.1e}, {B_hi:.1e}]{band_note}; "
                   f"conservative (upper-bound) margin ×{margin_hi:.2f}."
                   if margin_hi is not None else
                   f"MC surrogate B={B:.2e}, 95% CI [{B_lo:.1e}, {B_hi:.1e}]{band_note}.")
                  + gb_note))

    def evaluate_all(self, mode: str,
                     analytical_results: Optional[List[EngineResult]] = None) -> List[EngineResult]:
        """Evaluate every path with the surrogate. In design mode model E sizes each solid wall
        from its own upper limit, and the wall's duct and maze paths are evaluated through the wall
        as designed; other paths use the analytical suggestion (design mode) or the declared build
        (check mode)."""
        from . import surrogate_e as se
        ar = {r.label: r for r in (analytical_results or [])}
        out: List[EngineResult] = []
        wall_by_id = {w.id: w for w in self.design.walls}
        sizes_walls = (mode == "design" and self.available() and se.is_model_e(self.bundle))
        for path in all_paths(self.design):     # each wall's own path comes before its openings
            wall = wall_by_id[path.wall_id]
            a = ar.get(path.label)
            if sizes_walls and path.kind == "wall":
                result = self._design_wall(path, wall, a)
                wall_by_id[wall.id] = replace(wall, thickness1_mm=_designed_thickness(result, a, wall))
                out.append(result)
                continue
            if path.kind in ("door", "window"):
                thickness = path.lead_equiv_mm
            elif mode == "design" and a is not None and a.suggested_thickness_mm is not None:
                thickness = a.suggested_thickness_mm      # evaluate the suggested wall
            else:
                thickness = wall.thickness1_mm
            out.append(self.evaluate(path, wall, thickness, analytical=a))
        return out


def _sum_lines(lines, answers: List[Optional[_Served]]) -> Optional[_Served]:
    """Sum per-line answers (principal first) with their weights; edges are summed edge by edge.

    Each line's edges are a calibrated 95% interval; their sums are not. They are the 95% edges of
    the sum when the lines' errors move together, and wider when the errors are near normal, but
    the only distribution-free floor is 1 - 5% x (lines served), 80% for I-131's four. No
    full-spectrum Monte Carlo labels exist to calibrate the sum; the note says so.

    A minor line the model cannot serve at this depth, either unbuilt or outside the domain, is
    bounded by the nearest harder line that it can serve. For lines of 100 keV and above, every
    material here attenuates a softer line more (`tests/test_room_surrogate.py` checks the
    coefficients), so the harder line's true transmission is above the softer one's, and its own
    upper edge covers it: the bound needs no monotonicity of the model itself. With no such line, or
    with the principal line outside the domain, the barrier is outside the domain.

    The group, factor and energy reported are those of the directly served line carrying most of
    the transmitted dose, and `mu_x` is the deepest line's, so the finite-beam flag sees every line.
    """
    import numpy as np
    from . import surrogate_e as se
    principal = answers[0]
    if principal is None:
        return None
    if not principal.inside:
        return principal
    served = [answer for answer in answers if answer is not None and answer.inside]
    chosen, substituted = [], []
    for (energy, _), answer in zip(lines, answers):
        if answer is None or not answer.inside:
            harder = [candidate for candidate in served if candidate.energy_keV > energy]
            if not harder:
                return replace(principal, inside=False)
            answer = min(harder, key=lambda candidate: candidate.energy_keV)
            substituted.append(energy)
        chosen.append(answer)
    weights = np.array([weight for _, weight in lines])
    direct = [(weight * 10.0 ** answer.logB, index)
              for index, ((energy, weight), answer) in enumerate(zip(lines, chosen))
              if energy not in substituted]
    dominant = chosen[max(direct)[1]]
    depths = [answer.mu_x for answer in answers if answer is not None and answer.mu_x is not None]
    return replace(dominant, substituted=tuple(substituted), mu_x=max(depths, default=None),
                   **{edge: se.combine_lines(weights, np.array([getattr(a, edge) for a in chosen]))
                      for edge in ("logB", "lo", "hi")})


def _designed_thickness(result: EngineResult, analytical: Optional[EngineResult],
                        wall: Wall) -> float:
    """The first-layer thickness a design-mode wall row was evaluated at: the surrogate's own size,
    else the analytical suggestion, else the declared thickness."""
    if result.suggested_thickness_mm is not None:
        return result.suggested_thickness_mm
    if analytical is not None and analytical.suggested_thickness_mm is not None:
        return analytical.suggested_thickness_mm
    return wall.thickness1_mm

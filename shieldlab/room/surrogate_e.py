"""
surrogate_e.py
==============
Features and 95% prediction interval for the model-E surrogate, the MC-trained model the paper
reports (15,417 training configurations, tested on 2,400 recorded before simulation).

Model E differs from the earlier eight-feature bundle in two ways this module has to reproduce
exactly, or the app would serve numbers the paper did not test:

  * it has four physical features on top of the eight design features, namely the thickness of
    each layer and of the whole barrier in mean free paths and the logarithm of the open fraction
    of a duct's line of sight;
  * it predicts the DEPARTURE from a physical baseline (uncollided attenuation plus line-of-sight
    streaming), so the served transmission is the model's output plus that baseline.

The arithmetic mirrors the research repository (`src/model_e.py`, `src/duct_streaming.py`,
`src/paper_a_error_budget.py`, `src/mondrian_band.py`). The research repository's
`src/build_app_bundle_e.py` replays all 2,400 sealed test predictions through this module and
refuses to package the bundle if anything drifts, and `tests/test_room_surrogate.py` pins three of
them here, so the app and the paper cannot diverge.
"""

from __future__ import annotations

import math
from typing import Dict, NamedTuple, Optional, Tuple

import numpy as np

from .. import data_loader as dl
from ..physics import transmission as tx

LN10 = math.log(10.0)

# mu/rho is tabulated for these four materials only; anything else is interpolated in log(zeff).
MU_ANCHORS = {"water": 7.4, "concrete": 13.0, "steel": 26.0, "lead": 82.0}

# The training detector is a 200 mm square block whose centre sits at the off-axis offset.
DET_HALF_MM = 100.0
DET_AREA_MM2 = 200.0 * 200.0
MIN_LOG_OPEN_FRACTION = -6.0

SCHEME = {"taxonomy": "deployed", "score": "absolute", "centre": "union"}


class MeasuredFactor(NamedTuple):
    """A broad-beam factor as Monte Carlo measured it.

    `rel_unc` is the measurement's one-sigma relative uncertainty. `unconverged_step` is the rise
    over the last widening step of a ladder that had not stopped rising, and zero for one that had:
    it is carried into the upper edge as an allowance for the rise still to come.
    """
    value: float
    rel_unc: float
    unconverged_step: float = 0.0


class FieldFactor(NamedTuple):
    """The factor a served transmission is multiplied by, and the edges of its 95% range."""
    value: float
    low: float
    high: float


# The finite-field deficit, measured by widening the training 0.5 m beam to 3.5 m (research
# repository, `hpc_campaign/CONVENTION3_SCORE.json` and `CONVENTION4_SCORE.json`, jobs 332285 and
# 333856/333857, mapped as `CONVENTION4_PLAN.md` fixed before any row ran); see `field_convention`.
# Lead converged at 1.109 and is served at 1.20, above the measurement and its uncertainty.
FIELD_CONVENTION = {"lead": MeasuredFactor(1.20, 0.0), "steel": MeasuredFactor(1.573, 0.0073)}
# Concrete's factor rises with depth, so it is carried as (mu*x, factor) points.
CONCRETE_FIELD_CONVENTION = ((4.0, MeasuredFactor(1.718, 0.0051, unconverged_step=0.011)),
                             (6.0, MeasuredFactor(1.895, 0.0056)),
                             (8.0, MeasuredFactor(2.068, 0.0073)))
Z95 = 1.96
GROUP_NAMES = ("standard", "beam_shadow", "deep_tail")

# Photon lines (keV, photons per decay; NNDC) of the nuclides that emit more than one line that
# matters for shielding. A nuclide not listed is served at the bundle's single line. Lines below the
# trained energy range are left out and the rest renormalised, which over-states the transmitted
# dose: a softer line is always the more attenuated one.
PHOTON_LINES = {
    "I-131": ((364.49, 0.815), (636.99, 0.0716), (284.31, 0.0606), (722.91, 0.0177),
              (80.19, 0.0262)),
    "Lu-177": ((208.37, 0.1036), (112.95, 0.0620)),
    "Ga-68": ((511.0, 1.7828), (1077.34, 0.0322)),
}
# Mass energy-absorption coefficient of dry air (cm2/g; NIST, Hubbell and Seltzer), so that each line
# is weighted by the air kerma it delivers unshielded.
AIR_MU_EN_RHO = ((80.0, 0.02407), (100.0, 0.02325), (150.0, 0.02496), (200.0, 0.02672),
                 (300.0, 0.02872), (400.0, 0.02949), (500.0, 0.02966), (600.0, 0.02953),
                 (800.0, 0.02882), (1000.0, 0.02789), (1250.0, 0.02666))


def kerma_weighted_lines(nuclide: str, low_keV: float, high_keV: float
                         ) -> Optional[Tuple[Tuple[float, float], ...]]:
    """(energy keV, weight) for each of the nuclide's lines inside [low, high], weights summing to 1.

    The weight is the share of unshielded air kerma: photons per decay x energy x mu_en/rho of air.
    None for a nuclide with no line table, which is then served at its one line.
    """
    lines = PHOTON_LINES.get(nuclide)
    if lines is None:
        return None
    energies, mu_en = zip(*AIR_MU_EN_RHO)
    kept = [(energy, per_decay * energy * math.exp(np.interp(math.log(energy), np.log(energies),
                                                             np.log(mu_en))))
            for energy, per_decay in lines if low_keV <= energy <= high_keV]
    total = sum(kerma for _, kerma in kept)
    return tuple((energy, kerma / total) for energy, kerma in kept)


def combine_lines(weights: np.ndarray, log10_b: np.ndarray) -> float:
    """log10 of the kerma-weighted sum of the lines' transmissions, kept at or below B = 1."""
    return min(float(np.log10(np.sum(weights * 10.0 ** log10_b))), 0.0)

_MU_CACHE: Dict[Tuple[float, float], float] = {}


def is_model_e(bundle: Optional[dict]) -> bool:
    """True for a bundle this module serves; the eight-feature bundle has no baseline."""
    return bool(bundle) and bundle.get("baseline") == "logB_streaming" and "band" in bundle


def mu_rho(zeff: float, energy_keV: float) -> float:
    """Mass attenuation coefficient at this effective atomic number, interpolated in log(zeff)."""
    key = (round(float(zeff), 3), float(energy_keV))
    if key not in _MU_CACHE:
        mats = dl.load("materials")
        names = sorted(MU_ANCHORS, key=lambda n: MU_ANCHORS[n])
        anchors = [float(tx.interp_mu_rho(energy_keV / 1000.0, mats["energy_grid_MeV"],
                                          mats["materials"][n]["mu_rho"])) for n in names]
        log_z = np.log([MU_ANCHORS[n] for n in names])
        _MU_CACHE[key] = float(np.exp(np.interp(math.log(float(zeff)), log_z, np.log(anchors))))
    return _MU_CACHE[key]


def open_fraction(duct_radius_mm: float, det_offset_mm: float) -> float:
    """Fraction of the detector face the duct's unattenuated pencil lands on.

    Zero for a solid wall and for a duct whose pencil clears the detector. A radius wider than the
    detector half-width is a geometry the expression was never checked against, so it is refused.
    """
    radius = float(duct_radius_mm or 0.0)
    offset = abs(float(det_offset_mm or 0.0))
    if radius <= 0.0:
        return 0.0
    if radius > DET_HALF_MM:
        raise ValueError(f"duct radius {radius} mm exceeds the detector half-width "
                         f"({DET_HALF_MM} mm); the open fraction is not modelled there")
    low = float(np.clip(offset - DET_HALF_MM, -radius, radius))
    high = float(np.clip(offset + DET_HALF_MM, -radius, radius))

    def antiderivative(x: float) -> float:
        height = math.sqrt(max(radius ** 2 - x ** 2, 0.0))
        return x * height + radius ** 2 * math.asin(min(max(x / radius, -1.0), 1.0))

    return float(np.clip((antiderivative(high) - antiderivative(low)) / DET_AREA_MM2, 0.0, 1.0))


def streaming_log10_b(open_frac: float, nmfp_total: float) -> float:
    """log10 of the baseline: the streamed pencil plus the attenuated wall."""
    if open_frac > 0.0:
        return float(np.log10(open_frac + (1.0 - open_frac) * math.exp(-nmfp_total)))
    return -nmfp_total / LN10


def design_row(bundle: dict, *, energy_keV: float, thickness_mm: float, duct_radius_mm: float,
               det_offset_mm: float, zeff: float, density_gcm3: float,
               layer2_thickness_mm: float = 0.0, layer2_zeff: float = 0.0,
               layer2_density_gcm3: float = 0.0) -> Tuple[np.ndarray, float, float]:
    """The feature row in the bundle's own order, its baseline in log10 B, and the barrier's mfp."""
    nmfp1 = mu_rho(zeff, energy_keV) * density_gcm3 * thickness_mm / 10.0
    nmfp2 = 0.0
    if layer2_thickness_mm > 0 and layer2_density_gcm3 > 0:
        z2 = layer2_zeff if layer2_zeff > 0 else MU_ANCHORS["concrete"]
        nmfp2 = mu_rho(z2, energy_keV) * layer2_density_gcm3 * layer2_thickness_mm / 10.0
    nmfp_total = nmfp1 + nmfp2
    fraction = open_fraction(duct_radius_mm, det_offset_mm)
    values = {
        "primary_energy_keV": energy_keV, "thickness_mm": thickness_mm,
        "duct_radius_mm": duct_radius_mm or 0.0, "det_offset_mm": det_offset_mm or 0.0,
        "zeff": zeff, "density_gcm3": density_gcm3,
        "layer2_thickness_mm": layer2_thickness_mm or 0.0, "layer2_zeff": layer2_zeff or 0.0,
        "nmfp1": nmfp1, "nmfp2": nmfp2, "nmfp_total": nmfp_total,
        "log_open_fraction": max(math.log10(max(fraction, 1e-300)), MIN_LOG_OPEN_FRACTION),
    }
    missing = [f for f in bundle["features"] if f not in values]
    if missing:
        raise KeyError(f"the bundle wants features this module does not build: {missing}")
    X = np.array([[values[f] for f in bundle["features"]]], dtype=float)
    return X, streaming_log10_b(fraction, nmfp_total), nmfp_total


def group_of(bundle: dict, det_offset_mm: float, logB: float) -> str:
    """The interval group a query falls in: deep tail takes precedence over the beam shadow."""
    thresholds = bundle["band"]["thresholds"]
    if logB < thresholds["deep_logB_max"]:
        return "deep_tail"
    if (det_offset_mm > thresholds["shadow_offset_mm"]
            and logB < thresholds["shadow_logB_max"]):
        return "beam_shadow"
    return "standard"


def field_convention(mu_x: Optional[float], *materials: Optional[str]) -> FieldFactor:
    """What a served transmission is multiplied by to reach a broad-beam equivalent, with its range.

    Every training label was scored under a 0.5 m square beam, which truncates lateral scatter and
    returns a transmission below the broad-beam one the shielding tables assume. That is the
    non-conservative direction, so a design that does not correct for it sizes the barrier too thin.
    Monte Carlo measured the deficit directly, by widening the beam to 3.5 m at fixed barrier and
    detector:

      * concrete rises with depth: 1.718 at mu*x 4 and 1.895 at mu*x 6 (511 keV), and 2.068 at
        mu*x 8 (364 keV; 511 keV read 2.060). Every ladder converged except mu*x 4, which rose
        0.011 over its last step, 2.5 to 3.5 m, and is served as measured with that step added to
        its upper edge. Between the points it is interpolated; below mu*x 4 it holds the mu*x 4
        value, which over-states a factor that rises with depth, and beyond mu*x 8 it holds the
        mu*x 8 value: an earlier 1.5 m study read 1.90, 1.81 and 2.01 at mu*x 8, 10 and 12, no
        clear rise;
      * steel converged at 1.573 at mu*x 8 and 511 keV (1.554 at 364 keV), measured at that depth
        only;
      * lead converged at 1.109 (511 keV) and read 1.06 at 364 keV. It is served at the 1.20 the
        app carried before, which stays above both and their uncertainty.

    The range is the measurement's 95% interval: each factor's Monte Carlo uncertainty, plus the
    unconverged step above. It is carried into the served interval's edges, not its point.

    Only 364 and 511 keV were measured; other lines take the same factors. A material other than
    lead and steel takes the concrete factor, the largest measured at every depth, because nothing
    here licenses a smaller one. A laminate takes the largest factor and edges among its layers at
    the barrier's total depth: how two layers combine was not measured, and the larger factor is the
    safe reading of that silence. An unknown depth takes the deepest value.
    """
    known = [m for m in materials if m]
    factors = [_factor_range(FIELD_CONVENTION[m]) if m in FIELD_CONVENTION
               else _concrete_range(mu_x) for m in known] or [_concrete_range(mu_x)]
    return FieldFactor(*(max(edge) for edge in zip(*factors)))


def _factor_range(measured: MeasuredFactor) -> FieldFactor:
    spread = Z95 * measured.rel_unc * measured.value
    return FieldFactor(measured.value, measured.value - spread,
                       measured.value + spread + measured.unconverged_step)


def _concrete_range(mu_x: Optional[float]) -> FieldFactor:
    depths = [depth for depth, _ in CONCRETE_FIELD_CONVENTION]
    ranges = [_factor_range(measured) for _, measured in CONCRETE_FIELD_CONVENTION]
    if mu_x is None:
        return ranges[-1]
    # np.interp holds the end values beyond the measured depths
    return FieldFactor(*(float(np.interp(mu_x, depths, edge)) for edge in zip(*ranges)))


def apply_field_convention(factor: FieldFactor, logB: float, lo: float,
                           hi: float) -> Tuple[float, float, float]:
    """Raise a served point and interval in log10 B to their broad-beam equivalent.

    The point takes the factor, and each edge takes the matching edge of the factor's range, so the
    factor's own uncertainty widens the interval. All three stay at or below B = 1.
    """
    return (min(logB + math.log10(factor.value), 0.0),
            min(lo + math.log10(factor.low), 0.0),
            min(hi + math.log10(factor.high), 0.0))


def serve(bundle: dict, X: np.ndarray, baseline_logB: float) -> Tuple[float, float, float, str]:
    """Point prediction and 95% interval in log10 B, plus the group that set the offset."""
    served, lo, hi, groups = serve_batch(bundle, X, np.array([baseline_logB]))
    return float(served[0]), float(lo[0]), float(hi[0]), groups[0]


def serve_batch(bundle: dict, X: np.ndarray, baseline_logB: np.ndarray
                ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, list]:
    """`serve` for many rows at once: one call per model instead of one per row.

    A tree ensemble costs about the same for one row as for two hundred, so a thickness search
    that served its candidates one at a time would take seconds per wall.
    """
    band = bundle["band"]
    for key, expected in SCHEME.items():
        if band.get(key) != expected:
            raise ValueError(f"this module serves only the {SCHEME} scheme; the bundle carries "
                             f"{key}={band.get(key)!r}")
    point = bundle["model"].predict(X)
    lo = np.minimum(bundle["q_lo"].predict(X), point)
    hi = np.maximum(bundle["q_hi"].predict(X), point)
    served_logB = point + baseline_logB
    offset_column = X[:, bundle["features"].index("det_offset_mm")]
    groups = [group_of(bundle, float(offset_mm), float(logB))
              for offset_mm, logB in zip(offset_column, served_logB)]
    offset = np.array([band["offsets"][group] for group in groups])
    edge_lo = lo - offset + baseline_logB
    edge_hi = np.minimum(hi + offset + baseline_logB, 0.0)
    return served_logB, edge_lo, edge_hi, groups

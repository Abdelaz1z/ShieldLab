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
from typing import Dict, Optional, Tuple

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

# The finite-field deficit, measured per material against AAPM TG-108 at 511 keV; see
# `field_convention_factor` for what it is and why the unmeasured materials take the largest value.
FIELD_CONVENTION_FACTOR = {"lead": 1.20, "concrete": 1.35, "steel": 1.37}
FIELD_CONVENTION_DEFAULT = 1.37
GROUP_NAMES = ("standard", "beam_shadow", "deep_tail")

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


def field_convention_factor(*materials: Optional[str]) -> float:
    """What a served transmission is multiplied by to reach a broad-beam equivalent.

    Every training label was scored under a 0.5 m square beam, which is narrower than the broad beam
    the shielding tables assume, so it truncates lateral scatter and returns a transmission below the
    tabulated one. The paper measures that deficit by fitting this work's tenth-value layers against
    AAPM TG-108 at 511 keV: a constant factor of 1.20 in lead, 1.35 in concrete and 1.37 in steel,
    with no trend in thickness. It is the non-conservative direction, so a design that does not apply
    it sizes the barrier too thin.

    Only those three materials were measured. Any other takes the largest measured value, because the
    deficit is smallest in lead and nothing here licenses a smaller one elsewhere. A laminate takes
    the largest factor among its layers, for the same reason: how two layers combine was not
    measured, and the larger factor is the safe reading of that silence.
    """
    known = [FIELD_CONVENTION_FACTOR.get(m, FIELD_CONVENTION_DEFAULT) for m in materials if m]
    return max(known) if known else FIELD_CONVENTION_DEFAULT


def apply_field_convention(factor: float, *log10_b: float) -> Tuple[float, ...]:
    """Raise transmissions in log10 B by the convention factor, keeping them at or below B = 1."""
    shift = math.log10(factor)
    return tuple(min(value + shift, 0.0) for value in log10_b)


def serve(bundle: dict, X: np.ndarray, baseline_logB: float) -> Tuple[float, float, float, str]:
    """Point prediction and 95% interval in log10 B, plus the group that set the offset."""
    band = bundle["band"]
    for key, expected in SCHEME.items():
        if band.get(key) != expected:
            raise ValueError(f"this module serves only the {SCHEME} scheme; the bundle carries "
                             f"{key}={band.get(key)!r}")
    point = float(bundle["model"].predict(X)[0])
    lo = min(float(bundle["q_lo"].predict(X)[0]), point)
    hi = max(float(bundle["q_hi"].predict(X)[0]), point)
    served_logB = point + baseline_logB
    group = group_of(bundle, float(X[0, bundle["features"].index("det_offset_mm")]), served_logB)
    offset = band["offsets"][group]
    edge_lo = lo - offset + baseline_logB
    edge_hi = min(hi + offset + baseline_logB, 0.0)
    return served_logB, edge_lo, edge_hi, group

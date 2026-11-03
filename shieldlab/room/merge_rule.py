"""
merge_rule.py
=============
How model E serves a wall of three layers: E-Domain-5's merge rule and its correction.

Model E reads a wall of at most two layers. E-Domain-5 (research `EDOMAIN5_PLAN.md`, scored in
`hpc_campaign/EDOMAIN5_SCORE.json`) tested a rule that folds three layers into two on 180 Monte Carlo
walls it never saw (gypsum|lead|gypsum, concrete|lead|gypsum, gypsum|lead|concrete,
brick|lead|gypsum, gypsum|concrete|gypsum, steel|lead|steel; 0.3-8 mfp; 140.5-511 keV): the rule
alone put 100% within x2 of Monte Carlo (RMSE 0.030 in log10 B), and with the correction below
100% (RMSE 0.021). The plan fixed beforehand that the app then merges and corrects.

`merge` and `moved_light_mass` are the research's `hpc_campaign/merge_rule.py`, unchanged. Layers
are listed source side first as (material, thickness mm, density g/cm3) of the simulated material.
"""
from __future__ import annotations

import math

import numpy as np

HEAVY = ("lead", "lead_glass", "lead_glass_rs520")
MIXABLE = ("concrete", "gypsum", "brick")
CONCRETE_DENSITY = 2.30

# log10 C = a_E + b_E * m, fitted on E-Domain-5's 120 fit rows per line E (keV), m the light mass per
# area (g/cm2) the rule carries across the heavy layer. The served transmission is divided by C.
CORRECTION = {
    140.5: (0.010055582966771384, -0.007165411348633799),
    208.0: (-0.00023645071545165872, -0.005849270187007963),
    364.0: (-0.01093119167093847, -0.004875254984215314),
    511.0: (-0.011375832689356997, -0.0031301443133978186),
}


def merge(layers: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    """The merged wall, source side first, as (material, thickness_mm, density_gcm3).

    Lead and lead glass are heavy and stay as they are. The other (light) layers merge into one at
    equal mass per area, of their common material if they share one and of concrete otherwise, in
    the place of the light layer with the most mass per area (on a tie, the one nearer the source).
    Raises ValueError outside the tested rule: more than one heavy layer, or light layers of
    different materials that are not all concrete, gypsum or brick.
    """
    if len(layers) <= 2:
        return list(layers)
    heavy = [i for i, (material, _, _) in enumerate(layers) if material in HEAVY]
    light = [i for i in range(len(layers)) if i not in heavy]
    if len(heavy) > 1:
        raise ValueError("the merge rule holds one heavy layer at most")
    materials = {layers[i][0] for i in light}
    if len(materials) > 1 and not materials <= set(MIXABLE):
        raise ValueError(f"light layers {sorted(materials)} do not merge under the rule")
    mass = [layers[i][1] * layers[i][2] for i in light]
    material, density = ((layers[light[0]][0], layers[light[0]][2]) if len(materials) == 1
                         else ("concrete", CONCRETE_DENSITY))
    merged = (material, sum(mass) / density, density)
    anchor = light[mass.index(max(mass))]
    if not heavy:
        return [merged]
    return [merged, layers[heavy[0]]] if anchor < heavy[0] else [layers[heavy[0]], merged]


def moved_light_mass(layers: list[tuple[str, float, float]]) -> float:
    """Mass per area (g/cm2) of light material the rule carries across the heavy layer: + toward the
    source, - away from it, 0 if there is no heavy layer."""
    merged = merge(layers)
    heavy = [i for i, (material, _, _) in enumerate(layers) if material in HEAVY]
    if not heavy or len(layers) <= 2:
        return 0.0
    h = heavy[0]
    in_front_before = sum(t * rho for i, (_, t, rho) in enumerate(layers) if i < h) / 10.0
    in_front_after = merged[0][1] * merged[0][2] / 10.0 if merged[0][0] not in HEAVY else 0.0
    return in_front_after - in_front_before


def log10_correction(energy_keV: float, moved_mass_gcm2: float) -> float:
    """log10 C for a merged wall at this line.

    The coefficients were fitted at 140.5, 208, 364 and 511 keV; between lines each is interpolated
    linearly in log(E), and outside them the end line's value is held (np.interp holds the ends).
    """
    lines = sorted(CORRECTION)
    log_e = np.log(lines)
    a = float(np.interp(math.log(energy_keV), log_e, [CORRECTION[e][0] for e in lines]))
    b = float(np.interp(math.log(energy_keV), log_e, [CORRECTION[e][1] for e in lines]))
    return a + b * moved_mass_gcm2

"""Oblique-incidence correction for model E, used by the field tier's wall equivalence.

Model E was trained at normal incidence. The field tier asks it for a ray crossing a wall at
angle theta as the same wall at the slant thickness t / cos(theta) (`field_surrogate._equivalent`).
That reading misses the photons scattered toward the wall's far face, which have a shorter way out
than the slant: 400 Monte Carlo rows simulated at 5-60 degrees (research
`datasets/nm_dataset_tierc_oblique.csv`, never in model E's training) transmit more than E' says
at the slant thickness, by up to 1.8x in deep concrete at 50-60 degrees, and by nothing in lead
below ~300 keV, where photoelectric absorption leaves little to scatter.

The correction is one fitted constant on a physical shape (research `src/fit_oblique_correction.py`,
`models/oblique_correction.json`):

    log10(MC / E' at the slant) = K * f_C * (s - 1) * n**2

  s    the path factor 1 / cos(theta);
  n    the barrier's depth along the slant, in mean free paths (model E's own `nmfp_total`);
  f_C  the share of attenuation that is Compton scattering, Klein-Nishina against the total
       mu/rho, weighted over the layers by their depth.

Under cross-validation it took the rows' scatter about E' at the slant from 0.067 to 0.018 in log10,
the same with a whole material held out of the fit. It is fitted for s <= 2 (60 degrees) and
n <= 7, and is held at those edges beyond them.
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple

import numpy as np

from . import surrogate_e as se

K = 0.009406                     # models/oblique_correction.json, fitted on the 400 rows
MAX_SLANT = 2.0
MAX_NMFP = 7.0
# Electrons per unit mass (Z/A) of the four mu/rho anchors (NIST): water, ordinary concrete,
# iron for steel, lead.
Z_OVER_A = {"water": 0.55508, "concrete": 0.50274, "steel": 0.46557, "lead": 0.39575}
AVOGADRO = 6.02214076e23
ELECTRON_RADIUS_CM = 2.8179403262e-13

Layer = Tuple[float, float, float]          # (zeff, density g/cm3, thickness mm at normal incidence)


def klein_nishina_cm2(energy_keV: float) -> float:
    """Total Klein-Nishina cross-section per electron."""
    k = energy_keV / 511.0
    log_term = math.log(1.0 + 2.0 * k)
    first = (1.0 + k) / k ** 2 * (2.0 * (1.0 + k) / (1.0 + 2.0 * k) - log_term / k)
    second = log_term / (2.0 * k) - (1.0 + 3.0 * k) / (1.0 + 2.0 * k) ** 2
    return 2.0 * math.pi * ELECTRON_RADIUS_CM ** 2 * (first + second)


def compton_fraction(zeff: float, energy_keV: float) -> float:
    """Compton share of mu/rho, interpolated in log(zeff) between the anchors as model E's mu/rho is."""
    names = sorted(se.MU_ANCHORS, key=se.MU_ANCHORS.get)
    shares = [min(1.0, AVOGADRO * Z_OVER_A[n] * klein_nishina_cm2(energy_keV)
                  / se.mu_rho(se.MU_ANCHORS[n], energy_keV)) for n in names]
    return float(np.interp(math.log(zeff), np.log([se.MU_ANCHORS[n] for n in names]), shares))


def shape(layers: Sequence[Layer], energy_keV: float, slant: float) -> float:
    """f_C * (s - 1) * n**2 for a wall of `layers` crossed at path factor `slant`, s and n held at
    their fitted edges."""
    depths = [se.mu_rho(z, energy_keV) * rho * t_mm * slant / 10.0 for z, rho, t_mm in layers]
    n = sum(depths)
    if n <= 0.0:
        return 0.0
    f_c = sum(d * compton_fraction(z, energy_keV) for d, (z, _, _) in zip(depths, layers)) / n
    return f_c * (min(slant, MAX_SLANT) - 1.0) * min(n, MAX_NMFP) ** 2


def log10_factor(layers: Sequence[Layer], energy_keV: float, slant: float) -> float:
    """log10 of (transmission at the angle) / (model E at the slant thickness)."""
    return K * shape(layers, energy_keV, slant)

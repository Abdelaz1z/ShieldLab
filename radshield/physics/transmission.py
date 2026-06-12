"""
transmission.py
===============
Broad-beam photon TRANSMISSION models. Each model answers one question:

    "What fraction B of the radiation gets through a thickness x of a material?"

B is dimensionless (0..1). x is always in MILLIMETRES in this engine.

Three models are provided, matching the three kinds of data we have:

  1. Archer model  -- diagnostic X-ray beams (kVp) and radionuclide fits.
                      B(x) = [ (1 + b/a) * exp(a*g*x) - b/a ] ^ (-1/g)
                      (Archer, Thornby & Bushong 1983; NCRP 147 Eq. A.2/A.3.)

  2. TVL model     -- megavoltage (LINAC/Co-60) and simple radionuclide shielding.
                      n = x1/TVL1 + (x - x1)/TVLe ; B = 10^(-n)
                      (IAEA SRS 47 Eq. 6 / NCRP 151.) If only one TVL is known,
                      TVL1 = TVLe.

  3. mu + buildup  -- generic mono-energetic photons through ANY material, using
                      NIST mass attenuation coefficients (mu/rho) with a buildup
                      factor B_up:  T = B_up * exp(-(mu/rho)*rho*x).

The functions are deliberately small and pure (no I/O) so they are easy to test
and to read. The data they consume comes from radshield.data via data_loader.
"""

from __future__ import annotations

import math
from typing import Optional

# ---------------------------------------------------------------------------
# 1) ARCHER three-parameter broad-beam model
# ---------------------------------------------------------------------------

def archer_transmission(x_mm: float, alpha: float, beta: float, gamma: float) -> float:
    """Transmission B through thickness x_mm using the Archer model.

    B(x) = [ (1 + beta/alpha) * exp(alpha*gamma*x) - beta/alpha ] ^ (-1/gamma)

    Parameters
    ----------
    x_mm  : barrier thickness in mm (x >= 0).
    alpha : fitted parameter (mm^-1), ~ asymptotic attenuation coefficient.
    beta  : fitted parameter (mm^-1).
    gamma : fitted parameter (dimensionless).

    Returns the transmitted fraction (1.0 at x=0).
    """
    if x_mm <= 0:
        return 1.0
    ba = beta / alpha
    # exponent can overflow for thick, strongly attenuating layers; guard it.
    arg = alpha * gamma * x_mm
    # math.exp overflows around arg ~ 709; for any arg that large B is ~0.
    if arg > 700:
        return 0.0
    inner = (1.0 + ba) * math.exp(arg) - ba
    if inner <= 0:
        # numerically the term has collapsed -> negligible transmission
        return 0.0
    return inner ** (-1.0 / gamma)


def archer_thickness_for_B(B_target: float, alpha: float, beta: float,
                           gamma: float) -> float:
    """Invert the Archer model: thickness (mm) needed to reach transmission B_target.

    Solving B = [ (1+b/a) e^{a g x} - b/a ]^{-1/g} for x gives a closed form:

        x = (1 / (alpha*gamma)) * ln( ( B^(-gamma) + b/a ) / (1 + b/a) )

    Returns 0 if the requested transmission is >= 1 (no shielding needed).
    """
    if B_target >= 1.0:
        return 0.0
    if B_target <= 0.0:
        return float("inf")
    ba = beta / alpha
    numerator = B_target ** (-gamma) + ba
    denominator = 1.0 + ba
    val = numerator / denominator
    if val <= 0:
        return float("inf")
    x = math.log(val) / (alpha * gamma)
    return max(0.0, x)


# ---------------------------------------------------------------------------
# 2) TENTH-VALUE-LAYER (TVL) model
# ---------------------------------------------------------------------------

def tvl_transmission(x_mm: float, tvl1_mm: float, tvle_mm: Optional[float] = None) -> float:
    """Transmission B through thickness x_mm using the two-TVL model.

    The first TVL (tvl1) accounts for the harder spectrum near the surface; all
    subsequent attenuation uses the equilibrium TVL (tvle). If tvle is None,
    tvle = tvl1 (single-TVL / pure broad-beam case).

        n = x1/TVL1 + (x - x1)/TVLe       (x1 = min(x, TVL1))
        B = 10^(-n)
    """
    if x_mm <= 0:
        return 1.0
    if tvle_mm is None:
        tvle_mm = tvl1_mm
    if x_mm <= tvl1_mm:
        n = x_mm / tvl1_mm
    else:
        n = 1.0 + (x_mm - tvl1_mm) / tvle_mm
    return 10.0 ** (-n)


def tvl_thickness_for_B(B_target: float, tvl1_mm: float,
                        tvle_mm: Optional[float] = None) -> float:
    """Invert the TVL model: thickness (mm) to reach transmission B_target.

    n = -log10(B_target). The first TVL covers n up to 1; beyond that use TVLe.
    """
    if B_target >= 1.0:
        return 0.0
    if B_target <= 0.0:
        return float("inf")
    if tvle_mm is None:
        tvle_mm = tvl1_mm
    n = -math.log10(B_target)
    if n <= 1.0:
        return n * tvl1_mm
    return tvl1_mm + (n - 1.0) * tvle_mm


# ---------------------------------------------------------------------------
# 3) GENERIC mono-energetic mu/rho + buildup model
# ---------------------------------------------------------------------------

def interp_mu_rho(energy_MeV: float, energy_grid: list, mu_rho_grid: list) -> float:
    """Log-log interpolate the mass attenuation coefficient mu/rho (cm^2/g).

    Photon mu/rho varies smoothly on a log-log scale away from absorption edges,
    so log-log interpolation is the standard approach. Clamps to the grid ends.
    """
    if energy_MeV <= energy_grid[0]:
        return mu_rho_grid[0]
    if energy_MeV >= energy_grid[-1]:
        return mu_rho_grid[-1]
    # find the bracketing grid points
    for i in range(1, len(energy_grid)):
        if energy_MeV <= energy_grid[i]:
            e0, e1 = energy_grid[i - 1], energy_grid[i]
            m0, m1 = mu_rho_grid[i - 1], mu_rho_grid[i]
            # interpolate in log space
            log_e = math.log(energy_MeV)
            f = (log_e - math.log(e0)) / (math.log(e1) - math.log(e0))
            log_m = math.log(m0) + f * (math.log(m1) - math.log(m0))
            return math.exp(log_m)
    return mu_rho_grid[-1]


def mu_buildup_transmission(x_mm: float, mu_rho_cm2_g: float, density_kg_m3: float,
                            buildup: float = 1.0) -> float:
    """Transmission through thickness x_mm for a mono-energetic beam.

        T = buildup * exp(-(mu/rho) * rho * x)

    Units are handled here:
        mu/rho  in cm^2/g
        rho     in kg/m^3  -> converted to g/cm^3 (divide by 1000)
        x       in mm      -> converted to cm     (divide by 10)
    """
    if x_mm <= 0:
        return 1.0
    rho_g_cm3 = density_kg_m3 / 1000.0
    x_cm = x_mm / 10.0
    mu_lin_per_cm = mu_rho_cm2_g * rho_g_cm3  # linear attenuation coefficient (1/cm)
    return buildup * math.exp(-mu_lin_per_cm * x_cm)


def hvl_to_tvl(hvl_mm: float) -> float:
    """Convert a half-value layer to a tenth-value layer assuming exponential
    attenuation: TVL = HVL * log2(10) = HVL * 3.3219."""
    return hvl_mm * (math.log(10.0) / math.log(2.0))


# ---------------------------------------------------------------------------
# Multi-layer combiner
# ---------------------------------------------------------------------------

def combined_transmission(layer_transmissions: list) -> float:
    """Combine per-layer transmission factors into one overall factor.

    Standard engineering approximation: the layers act in series, so the total
    transmission is the PRODUCT of the individual broad-beam transmissions.

        B_total = B_1 * B_2 * ... * B_n

    This is slightly conservative for the secondary/leakage component because it
    ignores spectral hardening between layers (each subsequent layer sees a
    somewhat harder, more penetrating spectrum). For design (where we want to be
    safe) this is the appropriate direction. The recommended layer ordering and
    this caveat are surfaced to the user.
    """
    total = 1.0
    for b in layer_transmissions:
        total *= b
    return total

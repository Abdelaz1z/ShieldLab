"""
beams.py
========
Bridges the DATASETS to the TRANSMISSION MODELS.

A `Beam` describes the radiation field we are shielding (its kind and energy and
whether we want the primary or secondary transmission data). Given a Beam and a
material + thickness, `transmission_of_layer()` selects the correct data row and
transmission model and returns the transmitted fraction B.

This is the single place that decides "which model + which numbers" for every
(modality, energy, material) combination, so the rest of the engine stays simple.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .. import data_loader as dl
from . import transmission as tx


# Beam kinds
KIND_DIAGNOSTIC = "diagnostic"     # polyenergetic kVp X-ray beam (Archer per-kVp or per-distribution)
KIND_MEGAVOLTAGE = "megavoltage"   # LINAC / Co-60 (TVL model)
KIND_RADIONUCLIDE = "radionuclide" # I-131, Tc-99m, F-18, Lu-177 (TVL/HVL broad-beam)
KIND_MONO = "mono"                 # generic mono-energetic photon (mu/rho + buildup)


@dataclass
class Beam:
    """Describes a radiation field for transmission purposes.

    Attributes
    ----------
    kind        : one of KIND_* above.
    component   : 'primary' or 'secondary' (which transmission dataset to use).
    kvp         : peak kilovoltage (diagnostic).
    distribution: NCRP 147 workload-distribution key (diagnostic, optional).
    mv_energy   : energy label for megavoltage, e.g. '6 MV', 'Co-60'.
    nuclide     : radionuclide key, e.g. 'I-131'.
    mono_energy_MeV : energy for the generic mono-energetic model.
    scatter_angle_deg : scatter angle for megavoltage patient-scatter TVL.
    """
    kind: str
    component: str = "primary"
    kvp: Optional[int] = None
    distribution: Optional[str] = None
    mv_energy: Optional[str] = None
    nuclide: Optional[str] = None
    mono_energy_MeV: Optional[float] = None
    scatter_angle_deg: Optional[float] = None


# ---------------------------------------------------------------------------
# helpers to pull the right parameter set out of the datasets
# ---------------------------------------------------------------------------

def _nearest_index(value, grid):
    """Index of the grid entry closest to `value` (used for kVp / energy lookup)."""
    return min(range(len(grid)), key=lambda i: abs(grid[i] - value))


def _diagnostic_archer_params(beam: Beam, material: str):
    """Return (alpha, beta, gamma) for a diagnostic beam + material.

    Preference order:
      * if a workload distribution is given -> use the per-distribution table
        (primary or secondary as requested);
      * else use the single-kVp secondary table at the nearest kVp.
    """
    data = dl.archer_diagnostic()
    if material not in data.get("materials_in_tables", []):
        return None  # this material has no diagnostic Archer fit

    if beam.distribution:
        block = data["primary"] if beam.component == "primary" else data["secondary_distribution"]
        order = block["_order"]
        if beam.distribution not in order:
            return None
        i = order.index(beam.distribution)
        mat = block[material]
        return mat["alpha"][i], mat["beta"][i], mat["gamma"][i]

    # fall back to single-kVp SECONDARY data (primary single-kVp not tabulated in NCRP 147)
    block = data["secondary_kvp"]
    kvp = beam.kvp if beam.kvp is not None else 100
    i = _nearest_index(kvp, block["kvp"])
    mat = block[material]
    return mat["alpha"][i], mat["beta"][i], mat["gamma"][i]


def _megavoltage_tvl(beam: Beam, material: str):
    """Return (tvl1_mm, tvle_mm) for a megavoltage beam + material.

    Uses SRS 47 Table 4 (single TVL -> tvl1 = tvle). For patient-scattered
    radiation at a known angle, uses the concrete scatter-TVL table (Table 11).
    """
    data = dl.tvl_megavoltage()
    energies = data["energies"]
    if beam.mv_energy not in energies:
        return None
    e = energies.index(beam.mv_energy)

    # patient-scatter secondary in concrete at a specified angle (Table 11)
    if beam.component == "scatter" and material == "concrete" and beam.scatter_angle_deg:
        tbl = data["tvl_patient_scatter_concrete"]
        ang = str(int(beam.scatter_angle_deg))
        if ang in tbl["values"]:
            v = tbl["values"][ang][e]
            return v, v

    key = "tvl_primary" if beam.component == "primary" else "tvl_leakage"
    block = data[key]
    if material not in block:
        return None
    v = block[material][e]
    return v, v


def _radionuclide_tvl(beam: Beam, material: str):
    """Return (tvl1_mm, tvle_mm) for a radionuclide + material (broad-beam TVL)."""
    data = dl.radionuclides()
    nuc = data["radionuclides"].get(beam.nuclide)
    if not nuc:
        return None
    shield = nuc.get("shielding", {})
    if material in shield and "TVL_mm" in shield[material]:
        v = shield[material]["TVL_mm"]
        return v, v
    return None


def _mono_params(beam: Beam, material: str):
    """Return (mu_rho, density) for the generic mono-energetic model, or None."""
    data = dl.materials()
    mat = data["materials"].get(material)
    if not mat:
        return None
    grid = data["energy_grid_MeV"]
    mu_rho_grid = mat.get("mu_rho")
    if not mu_rho_grid:
        return None
    energy = beam.mono_energy_MeV if beam.mono_energy_MeV else 0.1
    mu_rho = tx.interp_mu_rho(energy, grid, mu_rho_grid)
    return mu_rho, mat["density_kg_m3"]


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def transmission_of_layer(beam: Beam, material: str, thickness_mm: float,
                          buildup: float = 1.0) -> float:
    """Transmitted fraction B through a single material layer for this beam.

    Picks the appropriate model based on beam.kind. Raises ValueError only if no
    data path exists for that (kind, material) combination, so callers can decide
    how to surface it.
    """
    if thickness_mm <= 0:
        return 1.0

    if beam.kind == KIND_DIAGNOSTIC:
        params = _diagnostic_archer_params(beam, material)
        if params:
            return tx.archer_transmission(thickness_mm, *params)
        # material without a diagnostic fit -> try generic mono at kVp/2 (mean energy proxy)
        beam2 = Beam(kind=KIND_MONO, mono_energy_MeV=((beam.kvp or 100) / 1000.0) * 0.5)
        return transmission_of_layer(beam2, material, thickness_mm, buildup)

    if beam.kind == KIND_MEGAVOLTAGE:
        tvl = _megavoltage_tvl(beam, material)
        if tvl:
            return tx.tvl_transmission(thickness_mm, tvl[0], tvl[1])
        raise ValueError(f"No megavoltage TVL data for material '{material}' at {beam.mv_energy}.")

    if beam.kind == KIND_RADIONUCLIDE:
        tvl = _radionuclide_tvl(beam, material)
        if tvl:
            return tx.tvl_transmission(thickness_mm, tvl[0], tvl[1])
        # fall back to mono-energetic at the principal gamma energy
        nuc = dl.radionuclides()["radionuclides"].get(beam.nuclide, {})
        e_keV = nuc.get("main_gamma_keV", 364)
        beam2 = Beam(kind=KIND_MONO, mono_energy_MeV=e_keV / 1000.0)
        return transmission_of_layer(beam2, material, thickness_mm, buildup)

    if beam.kind == KIND_MONO:
        mp = _mono_params(beam, material)
        if mp:
            return tx.mu_buildup_transmission(thickness_mm, mp[0], mp[1], buildup)
        raise ValueError(f"No mu/rho data for material '{material}'. Add a mu_rho grid in materials.json.")

    raise ValueError(f"Unknown beam kind '{beam.kind}'.")


def available_materials(beam: Beam) -> list:
    """List materials that have usable transmission data for this beam kind."""
    if beam.kind == KIND_DIAGNOSTIC:
        return list(dl.archer_diagnostic().get("materials_in_tables", []))
    if beam.kind == KIND_MEGAVOLTAGE:
        return list(dl.tvl_megavoltage().get("tvl_primary", {}).keys() - {"_comment", "ref", "table"})
    if beam.kind == KIND_RADIONUCLIDE:
        nuc = dl.radionuclides()["radionuclides"].get(beam.nuclide, {})
        return list(nuc.get("shielding", {}).keys() - {"ref"})
    if beam.kind == KIND_MONO:
        return [m for m, v in dl.materials()["materials"].items() if v.get("mu_rho")]
    return []

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

from dataclasses import dataclass
import math
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

def diagnostic_table_kvp(kvp: float) -> int:
    """Upper tabulated kVp within the covered range; never silently round down."""
    grid = dl.archer_diagnostic()["secondary_kvp"]["kvp"]
    if not math.isfinite(kvp) or not grid[0] <= kvp <= grid[-1]:
        raise ValueError(f"Diagnostic kVp must be within {grid[0]}-{grid[-1]}.")
    return next(potential for potential in grid if potential >= kvp)


def _diagnostic_archer_params(beam: Beam, material: str):
    """Return (alpha, beta, gamma) for a diagnostic beam + material.

    Preference order:
      * if a workload distribution is given -> use the per-distribution table
        (primary or secondary as requested);
      * else use the single-kVp secondary table at the upper tabulated kVp.
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
    i = block["kvp"].index(diagnostic_table_kvp(kvp))
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


def mu_rho_grid_for(material: str):
    """Return (energy_grid_MeV, mu_rho, max_valid_MeV) for a material, or None.

    Materials may carry their own `energy_grid_MeV` instead of the shared one, so a
    grid can stop where its source data stops. `mu_rho_max_energy_MeV` marks that
    limit explicitly: beyond it the coefficients are not merely uncertain, they are
    absent, and clamping to the last point would quietly under-attenuate.
    """
    data = dl.materials()
    mat = data["materials"].get(material)
    if not mat:
        return None
    mu_rho = mat.get("mu_rho")
    if not mu_rho:
        return None
    grid = mat.get("energy_grid_MeV") or data["energy_grid_MeV"]
    limit = mat.get("mu_rho_max_energy_MeV", grid[-1])
    return grid, mu_rho, limit


def _mono_params(beam: Beam, material: str):
    """Return (mu_rho, density) for the generic mono-energetic model, or None."""
    entry = mu_rho_grid_for(material)
    if entry is None:
        return None
    grid, mu_rho_grid, limit = entry
    energy = _fallback_energy(beam)
    if not math.isfinite(energy) or not grid[0] <= energy <= limit:
        return None                    # outside the tabulated range: no data, not a guess
    mat = dl.materials()["materials"][material]
    if not tx.mu_rho_interpolation_supported(energy, grid, mat.get("absorption_edges_MeV", [])):
        return None
    return tx.interp_mu_rho(energy, grid, mu_rho_grid), mat["density_kg_m3"]


def _fallback_energy(beam: Beam) -> float:
    if beam.kind == KIND_DIAGNOSTIC:
        return (beam.kvp if beam.kvp is not None else 100) / 2000.0
    if beam.kind == KIND_RADIONUCLIDE:
        return dl.radionuclides()["radionuclides"][beam.nuclide]["main_gamma_keV"] / 1000.0
    return beam.mono_energy_MeV if beam.mono_energy_MeV is not None else 0.1


def _validate_buildup_table(table) -> None:
    if not isinstance(table, dict):
        raise ValueError("Build-up tables must be objects with energy and geometry.")
    tx.validate_buildup_grid(table.get("mux", []), table.get("B", []))
    energy = table.get("energy_MeV", 0)
    if (table.get("quantity") != "air_kerma" or not table.get("geometry")
            or not table.get("ref") or not isinstance(energy, (int, float))
            or not math.isfinite(energy) or energy <= 0):
        raise ValueError("Build-up tables require energy, air_kerma quantity, geometry and ref.")


def _buildup_table(material: str, energy_MeV: float):
    """Only exact-energy, documented air-kerma tables may supply a correction."""
    mat = dl.materials()["materials"].get(material) or {}
    if "buildup_mux" in mat or "buildup_B" in mat:
        raise ValueError("Legacy build-up arrays lack energy and geometry; use buildup_tables.")
    tables = mat.get("buildup_tables", [])
    if not isinstance(tables, list):
        raise ValueError("buildup_tables must be a list.")
    for table in tables:
        _validate_buildup_table(table)
        if math.isclose(table["energy_MeV"], energy_MeV, rel_tol=1e-9):
            return table
    return None


def has_buildup_data(material: str, energy_MeV: float) -> bool:
    return _buildup_table(material, energy_MeV) is not None


def _mono_buildup(beam: Beam, material: str, thickness_mm: float) -> float:
    """Dose build-up factor for this barrier, or 1.0 (narrow beam) if untabulated."""
    table = _buildup_table(material, _fallback_energy(beam))
    if table is None:
        return 1.0
    mu_rho_cm2_g, density_kg_m3 = _mono_params(beam, material)
    mu_x = mu_rho_cm2_g * (density_kg_m3 / 1000.0) * (thickness_mm / 10.0)
    return tx.interp_buildup(mu_x, table["mux"], table["B"])


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def transmission_of_layer(beam: Beam, material: str, thickness_mm: float,
                          buildup: Optional[float] = None) -> float:
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
            # An explicit buildup argument wins; otherwise use the material's own
            # table when it has one, and fall back to 1.0 (narrow beam) when it
            # does not. data_path() reports which of those two applied.
            factor = buildup if buildup is not None else _mono_buildup(beam, material, thickness_mm)
            return tx.mu_buildup_transmission(thickness_mm, mp[0], mp[1], factor)
        raise ValueError(f"No mu/rho data for material '{material}'. Add a mu_rho grid in materials.json.")

    raise ValueError(f"Unknown beam kind '{beam.kind}'.")


# ---------------------------------------------------------------------------
# which dataset serves a (beam, material) pair
# ---------------------------------------------------------------------------

PATH_BROAD = "broad"      # a measured broad-beam dataset (Archer fit or TVL) exists
PATH_NARROW = "narrow"    # only the generic mu/rho model applies -- see the caveat below
PATH_BUILDUP = "buildup"  # documented correction; still not a measured broad-beam fit
PATH_NONE = None          # no data at all; this material cannot be evaluated


def data_path(beam: Beam, material: str) -> Optional[str]:
    """Which kind of transmission data serves this (beam, material) pair.

    PATH_BROAD  the referenced broad-beam dataset covers it (Archer fit for
                diagnostic beams, TVL for megavoltage and radionuclides). These
                already include scatter build-up and are what the standards
                intend for barrier design.
    PATH_NARROW only the generic mu/rho model applies. Without a build-up factor
                that model is NARROW-beam: it counts photons removed from the
                beam but not those scattered back into it, so it UNDER-predicts
                the dose behind a thick barrier. Callers must label it.
    PATH_NONE   no dataset reaches this pair; evaluating it would raise.
    PATH_BUILDUP a documented generic correction, still requiring model review.

    This is the single source of truth for "can we shield X with Y, and how well
    do we know it" -- `transmission_of_layer`, the UI material lists and the
    result warnings all read it, so they cannot drift apart.
    """
    if beam.kind == KIND_DIAGNOSTIC:
        if _diagnostic_archer_params(beam, material):
            return PATH_BROAD
    elif beam.kind == KIND_MEGAVOLTAGE:
        # No mono fallback exists for megavoltage: mu/rho at MV energies without
        # build-up is wrong by orders of magnitude, so it is not offered at all.
        return PATH_BROAD if _megavoltage_tvl(beam, material) else PATH_NONE
    elif beam.kind == KIND_RADIONUCLIDE:
        if _radionuclide_tvl(beam, material):
            return PATH_BROAD
    elif beam.kind != KIND_MONO:
        return PATH_NONE                       # unknown beam kind: nothing serves it

    # diagnostic, radionuclide and mono beams all fall back to the generic grid
    if not _mono_params(beam, material):
        return PATH_NONE
    # A correction table is not equivalent to a measured broad-beam fit.
    return PATH_BUILDUP if has_buildup_data(material, _fallback_energy(beam)) else PATH_NARROW


def available_materials(beam: Beam) -> list:
    """Materials this beam can actually be shielded with, in materials.json order.

    Ordering is taken from materials.json rather than from a set operation, so the
    list is stable across runs -- a UI can use it to populate a control without the
    default selection moving between restarts.
    """
    return [
        m for m in dl.materials()["materials"]
        if data_path(beam, m) is not PATH_NONE
    ]


def narrow_beam_materials(beam: Beam) -> list:
    """Subset of `available_materials` served only by the generic mu/rho model.

    Results for these are narrow-beam and therefore optimistic; the caller is
    expected to say so rather than presenting them like the tabulated ones.
    """
    return [
        m for m in dl.materials()["materials"]
        if data_path(beam, m) == PATH_NARROW
    ]


def available_materials_for(beams) -> list:
    """Materials usable for EVERY beam in `beams`, in materials.json order.

    A barrier is attenuated against each of a source's component beams in turn, so
    a material is only safe to offer if all of them can be evaluated -- one gap is
    enough to raise part-way through and lose the whole result.
    """
    beams = list(beams)
    all_materials = list(dl.materials()["materials"])
    if not beams:
        return all_materials
    return [
        m for m in all_materials
        if all(data_path(b, m) is not PATH_NONE for b in beams)
    ]


def narrow_beam_materials_for(beams) -> list:
    """Usable materials that fall back to the narrow-beam model for any of `beams`."""
    beams = list(beams)
    return [
        m for m in available_materials_for(beams)
        if any(data_path(b, m) == PATH_NARROW for b in beams)
    ]

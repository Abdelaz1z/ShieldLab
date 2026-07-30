"""
optimize.py
===========
Cost / material optimiser — turns "how much shielding?" into "which material is the
CHEAPEST way to meet the goal, and what does it cost in money, weight and space?".

For a given source term and design goal it takes every candidate material that has a
usable transmission path, asks the solver for the thickness that just meets the goal,
then attaches the installed cost (materials_cost.json), the structural areal load
(density x thickness) and the wall depth. The options are ranked cheapest-first and the
best-for-cost / best-for-weight / best-for-space choices are flagged.

This is a PLANNING aid for RELATIVE comparison. The cost figures are representative,
editable estimates — every ranking must be confirmed with local quotations and a
structural engineer (see the disclaimer in materials_cost.json).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .. import data_loader as dl
from . import barriers as ba
from . import solver
from ..regulatory import limits as reg
from . import sources as src


@dataclass
class MaterialOption:
    material: str
    label: str
    required_mm: float          # exact solver thickness to meet goal/T
    preferred_mm: float         # rounded up to a practical increment
    cost_per_m2_usd: float      # installed cost of 1 m^2 of wall at preferred_mm
    cost_low_usd: float
    cost_high_usd: float
    weight_per_m2_kg: float     # structural areal load
    space_mm: float             # wall depth this material needs
    feasible: bool              # thickness within a buildable limit
    already_met: bool           # goal met with 0 mm of this material
    note: str = ""
    is_cheapest: bool = False
    is_lightest: bool = False
    is_thinnest: bool = False


def rank_options(source: src.SourceTerm, goal: reg.DesignGoal,
                 candidates: Optional[List[str]] = None,
                 existing: Optional[ba.Barrier] = None,
                 max_buildable_mm: float = 3000.0) -> List[MaterialOption]:
    """Rank candidate materials cheapest-first for meeting `goal` against `source`.

    A material is skipped only if it has NO transmission data for this beam (the solver
    raises) or NO cost entry. Materials that cannot practically reach the goal come out
    with feasible=False and sort last, so the caller can still show them greyed out.
    """
    mats = dl.materials()["materials"]
    costs = dl.materials_cost()["materials"]
    if candidates is None:
        candidates = list(mats.keys())

    opts: List[MaterialOption] = []
    for m in candidates:
        if m not in mats or m not in costs:
            continue
        c = costs[m]
        if "installed_cost_usd_per_m3" not in c:
            continue
        try:
            req = solver.required_thickness(source, m, goal, existing=existing)
        except Exception:
            continue  # no usable transmission path for this (beam, material)

        pref = solver.preferred_thickness(req, m)
        density = mats[m]["density_kg_m3"]
        cpm3 = c["installed_cost_usd_per_m3"]
        lo, hi = c.get("range_usd_per_m3", [cpm3, cpm3])
        thick_m = pref / 1000.0
        opts.append(MaterialOption(
            material=m, label=mats[m].get("label", m),
            required_mm=req, preferred_mm=pref,
            cost_per_m2_usd=thick_m * cpm3,
            cost_low_usd=thick_m * lo, cost_high_usd=thick_m * hi,
            weight_per_m2_kg=thick_m * density, space_mm=pref,
            feasible=(req <= max_buildable_mm), already_met=(req <= 0.0),
            note=c.get("labour_note", "")))

    # cheapest first; unbuildable options sink to the bottom
    opts.sort(key=lambda o: (not o.feasible, o.cost_per_m2_usd))

    buildable = [o for o in opts if o.feasible and not o.already_met]
    if buildable:
        min(buildable, key=lambda o: o.cost_per_m2_usd).is_cheapest = True
        min(buildable, key=lambda o: o.weight_per_m2_kg).is_lightest = True
        min(buildable, key=lambda o: o.space_mm).is_thinnest = True
    return opts


def headline(options: List[MaterialOption]) -> Optional[str]:
    """One-line recommendation from a ranked list (or None if nothing is buildable)."""
    buildable = [o for o in options if o.feasible and not o.already_met]
    if not buildable:
        return None
    cheap = next(o for o in buildable if o.is_cheapest)
    thin = next(o for o in buildable if o.is_thinnest)
    msg = (f"Cheapest: {cheap.preferred_mm:g} mm {cheap.label} "
           f"(~${cheap.cost_per_m2_usd:,.0f}/m², {cheap.weight_per_m2_kg:,.0f} kg/m²).")
    if thin.material != cheap.material:
        factor = thin.cost_per_m2_usd / cheap.cost_per_m2_usd if cheap.cost_per_m2_usd else 0
        msg += (f"  Most compact: {thin.preferred_mm:g} mm {thin.label} "
                f"({thin.space_mm:g} mm vs {cheap.space_mm:g} mm — {factor:.0f}× the cost).")
    return msg

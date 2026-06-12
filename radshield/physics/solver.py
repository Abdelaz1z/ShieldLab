"""
solver.py
=========
Ties the pieces together:

    source term (unshielded dose)  +  barrier (layers)  +  design goal
        -> transmitted dose per component and total
        -> pass/fail verdict and safety margin
        -> required single-material thickness to just meet the goal
        -> preferred (rounded, practical) thickness
        -> lead / concrete equivalent of any barrier

`evaluate()` answers the user's core question: "for THIS combination of
materials and thicknesses, what gets through, is it acceptable, and what is the
scattered (secondary) component?"  `required_thickness()` answers "what
thickness of material X do I need?"
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import barriers as ba
from . import beams as bm
from . import sources as src
from ..regulatory import limits as reg


@dataclass
class ComponentResult:
    name: str
    unshielded: float
    transmission: float
    transmitted: float
    detail: str = ""


@dataclass
class Evaluation:
    """Full result of evaluating a barrier against a source and goal."""
    components: List[ComponentResult]
    transmitted_total: float
    transmitted_secondary: float      # scatter + leakage only (the "scattered radiation")
    verdict: reg.Verdict
    unit: str
    barrier_description: str
    areal_density_kg_m2: float
    equivalents: Dict[str, float] = field(default_factory=dict)  # mm Pb / mm concrete
    notes: List[str] = field(default_factory=list)


def evaluate(source: src.SourceTerm, barrier: ba.Barrier,
             goal: reg.DesignGoal,
             equivalent_materials=("lead", "concrete")) -> Evaluation:
    """Evaluate a specific barrier against the source and design goal.

    For each unshielded component the barrier transmission is computed with that
    component's own beam (primary vs secondary attenuate differently), then the
    transmitted doses are summed and compared with P/T.
    """
    comp_results: List[ComponentResult] = []
    secondary_names = {"scatter", "leakage", "secondary"}
    transmitted_secondary = 0.0

    for c in source.components:
        B = barrier.transmission(c.beam)
        transmitted = c.unshielded * B
        comp_results.append(ComponentResult(c.name, c.unshielded, B, transmitted, c.detail))
        if c.name in secondary_names:
            transmitted_secondary += transmitted

    transmitted_total = sum(cr.transmitted for cr in comp_results)
    v = reg.verdict(transmitted_total, goal)

    # Express the required attenuation as an equivalent single-material thickness.
    # Equivalent thickness = thickness of that one material giving the SAME total
    # transmitted dose as this barrier (matched on the dominant component).
    equivalents = {}
    if source.components:
        # use the component with the largest transmitted dose for the equivalence beam
        dominant = max(comp_results, key=lambda cr: cr.transmitted)
        dom_beam = next(c.beam for c in source.components if c.name == dominant.name)
        B_overall = (transmitted_total / source.total_unshielded()) if source.total_unshielded() > 0 else 1.0
        for m in equivalent_materials:
            try:
                equivalents[m] = ba.equivalent_thickness_mm(dom_beam, B_overall, m)
            except Exception:
                pass

    ev = Evaluation(
        components=comp_results,
        transmitted_total=transmitted_total,
        transmitted_secondary=transmitted_secondary,
        verdict=v,
        unit=source.unit,
        barrier_description=barrier.describe(),
        areal_density_kg_m2=barrier.areal_density_kg_m2(),
        equivalents=equivalents,
        notes=list(source.notes),
    )
    return ev


def required_thickness(source: src.SourceTerm, material: str,
                       goal: reg.DesignGoal,
                       existing: Optional[ba.Barrier] = None,
                       x_hi_mm: float = 5000.0) -> float:
    """Minimum thickness (mm) of one material to bring the TOTAL transmitted dose
    to the goal P/T, optionally on top of an existing barrier.

    Solved by bisection because different components attenuate differently, so
    the total transmitted dose is a sum of decaying terms (monotonic in x).
    Returns 0 if the goal is already met with no added material.
    """
    goal_over_T = goal.P_weekly / goal.occupancy_T if goal.occupancy_T > 0 else goal.P_weekly

    def transmitted_with(x_mm: float) -> float:
        total = 0.0
        for c in source.components:
            B_existing = existing.transmission(c.beam) if existing else 1.0
            B_new = bm.transmission_of_layer(c.beam, material, x_mm)
            total += c.unshielded * B_existing * B_new
        return total

    if transmitted_with(0.0) <= goal_over_T:
        return 0.0  # already acceptable without this material

    lo, hi = 0.0, x_hi_mm
    # expand hi until it over-attenuates
    for _ in range(10):
        if transmitted_with(hi) <= goal_over_T:
            break
        hi *= 2
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if transmitted_with(mid) > goal_over_T:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-3:
            break
    return hi  # hi side guarantees the goal is met


def preferred_thickness(required_mm: float, material: str) -> float:
    """Round a required thickness UP to a practical/standard increment.

    Standard construction increments by material:
        lead        -> 0.5 mm (sheet lead codes)
        concrete    -> 10 mm
        steel       -> 1 mm
        others      -> 1 mm
    Always rounds up so the goal stays satisfied.
    """
    increments = {"lead": 0.5, "concrete": 10.0, "barite_concrete": 10.0,
                  "steel": 1.0, "gypsum": 1.0, "plate_glass": 1.0,
                  "lead_glass": 1.0, "wood": 5.0, "brick": 10.0}
    inc = increments.get(material, 1.0)
    if required_mm <= 0:
        return 0.0
    return math.ceil(required_mm / inc) * inc

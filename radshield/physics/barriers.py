"""
barriers.py
===========
A BARRIER is an ordered list of material LAYERS (e.g. 150 mm concrete + 2 mm
lead). This module computes the combined transmission of a barrier for a given
beam, the areal weight, and the lead/concrete "equivalent thickness" used to
communicate the result.

The combined transmission is the product of the per-layer broad-beam factors
(see transmission.combined_transmission for the rationale and caveat).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .. import data_loader as dl
from . import beams as bm
from . import transmission as tx


@dataclass
class Layer:
    """One material layer in a barrier."""
    material: str          # key into materials.json, e.g. 'concrete'
    thickness_mm: float    # layer thickness in millimetres


@dataclass
class Barrier:
    """An ordered stack of layers (listed from source side to occupied side)."""
    layers: List[Layer] = field(default_factory=list)

    def add(self, material: str, thickness_mm: float) -> "Barrier":
        """Append a layer (returns self so calls can be chained)."""
        self.layers.append(Layer(material, thickness_mm))
        return self

    # --- transmission --------------------------------------------------------

    def layer_transmissions(self, beam: bm.Beam) -> List[float]:
        """Transmission factor of each layer for the given beam."""
        return [
            bm.transmission_of_layer(beam, layer.material, layer.thickness_mm)
            for layer in self.layers
        ]

    def transmission(self, beam: bm.Beam) -> float:
        """Combined transmission B of the whole barrier (product of layers)."""
        return tx.combined_transmission(self.layer_transmissions(beam))

    # --- physical descriptors ------------------------------------------------

    def areal_density_kg_m2(self) -> float:
        """Mass per unit area (kg/m^2) = sum of density * thickness over layers.

        A useful proxy for the structural load the barrier puts on the building.
        """
        mats = dl.materials()["materials"]
        total = 0.0
        for layer in self.layers:
            rho = mats.get(layer.material, {}).get("density_kg_m3", 0.0)
            total += rho * (layer.thickness_mm / 1000.0)  # mm -> m
        return total

    def total_thickness_mm(self) -> float:
        return sum(layer.thickness_mm for layer in self.layers)

    def describe(self) -> str:
        """Human-readable one-line description of the barrier."""
        if not self.layers:
            return "(no barrier)"
        return " + ".join(f"{l.thickness_mm:g} mm {l.material}" for l in self.layers)


def equivalent_thickness_mm(beam: bm.Beam, B_target: float, material: str) -> float:
    """Thickness of a SINGLE material that gives transmission B_target for this beam.

    Used to express any barrier as an "equivalent mm of lead" or "equivalent mm
    of concrete", which is how shielding results are usually communicated.
    Uses the analytic inverse where available, else a bracketed numeric search.
    """
    if B_target >= 1.0:
        return 0.0

    # Analytic inverses where we have closed forms ------------------------
    if beam.kind == bm.KIND_DIAGNOSTIC:
        params = bm._diagnostic_archer_params(beam, material)
        if params:
            return tx.archer_thickness_for_B(B_target, *params)
    if beam.kind == bm.KIND_MEGAVOLTAGE:
        tvl = bm._megavoltage_tvl(beam, material)
        if tvl:
            return tx.tvl_thickness_for_B(B_target, tvl[0], tvl[1])
    if beam.kind == bm.KIND_RADIONUCLIDE:
        tvl = bm._radionuclide_tvl(beam, material)
        if tvl:
            return tx.tvl_thickness_for_B(B_target, tvl[0], tvl[1])

    # Generic fallback: numeric bisection on thickness --------------------
    return _numeric_thickness_for_B(beam, material, B_target)


def _numeric_thickness_for_B(beam: bm.Beam, material: str, B_target: float,
                             x_hi_mm: float = 5000.0, tol: float = 1e-4) -> float:
    """Bisection search for the thickness giving B_target (monotonic in x)."""
    lo, hi = 0.0, x_hi_mm
    # make sure hi is thick enough to over-attenuate; expand if needed
    for _ in range(8):
        if bm.transmission_of_layer(beam, material, hi) <= B_target:
            break
        hi *= 2
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        B = bm.transmission_of_layer(beam, material, mid)
        if abs(B - B_target) / B_target < tol:
            return mid
        if B > B_target:      # too much getting through -> need more thickness
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)

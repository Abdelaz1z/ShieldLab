"""The materials the Monte Carlo actually simulated, and how a real product maps onto them.

Every model in this package that was trained on Monte Carlo labels learned the physics of the
Geant4 material behind each name, at that material's density, whatever density a manifest or this
package's material table records. The table below is read from the production container
(GATE 10.1 / Geant4 11.4.1) and from `spike_slab.py`; see thesis_mc/MATERIALS_GROUND_TRUTH.md.

A product of the same composition but a different density - gypsum wallboard against solid
gypsum, a 2.35 g/cm3 concrete against Geant4's 2.30 - attenuates exactly like the simulated
material at the thickness carrying the same mass per unit area, because mass attenuation depends
on composition alone. Serving the product's own thickness instead treats wallboard as a wall 2.9
times heavier, which under-predicts transmission.
"""
from __future__ import annotations

from typing import Optional

from .. import data_loader

# Geant4 material and density (g/cm3) behind each name the models were trained on.
SIMULATED = {
    "lead": ("G4_Pb", 11.35),
    "concrete": ("G4_CONCRETE", 2.30),
    "steel": ("G4_STAINLESS-STEEL", 8.00),
    "gypsum": ("G4_GYPSUM, solid", 2.32),
    "lead_glass": ("G4_GLASS_LEAD", 6.22),
    "barite_concrete": ("PNNL-15870 barite concrete BA", 3.35),
    "brick": ("PNNL-15870 common silica brick", 1.80),
}

# Lead glass gets lighter by carrying less lead, so its mass attenuation falls with its density
# and equal mass per area is not equal attenuation. It is served only at the simulated density.
COMPOSITION_TRACKS_DENSITY = frozenset({"lead_glass"})
SAME_DENSITY_TOLERANCE = 0.005
NOTE_THRESHOLD = 0.005


def product_density_gcm3(material: str) -> Optional[float]:
    """Density of the product the user builds with, from the package's material table."""
    entry = data_loader.load("materials")["materials"].get(material)
    if entry is None or not entry.get("density_kg_m3"):
        return None
    return float(entry["density_kg_m3"]) / 1000.0


def simulated_thickness_mm(material: str, thickness_mm: float) -> Optional[float]:
    """Thickness of the simulated material with the product's mass per unit area.

    None means no rescaling is valid: the material was never simulated, its product density is
    unknown, or its composition changes with density and the two densities differ.
    """
    simulated = SIMULATED.get(material)
    product = product_density_gcm3(material)
    if simulated is None or product is None:
        return None
    ratio = product / simulated[1]
    if material in COMPOSITION_TRACKS_DENSITY and abs(ratio - 1.0) > SAME_DENSITY_TOLERANCE:
        return None
    return float(thickness_mm) * ratio


def served_as_note(layers: list[tuple[str, float]]) -> str:
    """Tell the user when a layer was served as a different thickness of the simulated material."""
    parts = []
    for material, thickness_mm in layers:
        served = simulated_thickness_mm(material, thickness_mm)
        if served is None or not thickness_mm:
            continue
        if abs(served / thickness_mm - 1.0) > NOTE_THRESHOLD:
            name, density = SIMULATED[material]
            parts.append(f"{thickness_mm:.1f} mm {material} as {served:.1f} mm of {name} "
                         f"({density:.2f} g/cm³)")
    if not parts:
        return ""
    return " Served at equal mass per area: " + "; ".join(parts) + "."

"""
radshield.room
==============
Room Designer (ShieldCAD MVP): the user describes a nuclear-medicine room as a
parametric layout (dimensions + source + four walls with their adjacent areas and
openings), and this package turns that into per-barrier shielding results — either
SUGGESTING the thickness needed (Design mode) or EVALUATING a declared barrier
(Check mode) — plus a live top-view diagram and an exportable report.

It is a thin layer ON TOP of the validated `radshield.physics` engine (NCRP-151 /
TG-108 broad-beam). Nothing here re-derives physics; the physics package is wrapped,
never modified. The surrogate tier (Extra-Trees + CQR + OOD guard from the thesis)
plugs into the same `EngineResult` interface in Phase B.
"""

from .model import (
    Room, Source, Opening, AdjacentArea, Wall, RoomDesign,
    WALL_IDS, ISOTOPES, OCCUPANCY_MENU,
)
from .engines import EngineResult, AnalyticalEngine

__all__ = [
    "Room", "Source", "Opening", "AdjacentArea", "Wall", "RoomDesign",
    "WALL_IDS", "ISOTOPES", "OCCUPANCY_MENU",
    "EngineResult", "AnalyticalEngine",
]

"""
model.py
========
The room data model: plain dataclasses that fully describe a room design, plus
JSON (de)serialization and validation. This schema IS the forward-compatible
contract for the whole ShieldCAD product (freehand canvas, DXF/IFC import, 3D
field maps all populate the same objects later), so keep it clean and explicit.

Units: metres for room/positions, millimetres for barrier thicknesses and
opening sizes, MBq for activity, minutes for residence time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# Wall identifiers, top view: origin at the SW corner, +x = East, +y = North.
WALL_IDS = ("N", "E", "S", "W")
WALL_NAMES = {"N": "North", "E": "East", "S": "South", "W": "West"}

# Isotopes the physics engine has radionuclide data for (radshield/data/radionuclides.json).
ISOTOPES = ("Tc-99m", "F-18", "I-131", "Lu-177")

# NCRP-151 Table B.1 occupancy factors, as a labelled menu for the UI.
OCCUPANCY_MENU = {
    "Full (offices, labs, control room) — 1": 1.0,
    "Adjacent treatment/exam room — 1/2": 0.5,
    "Corridor, staff lounge — 1/5": 0.2,
    "Corridor door, public toilet — 1/8": 0.125,
    "Waiting room, stairway, unattended lift — 1/20": 0.05,
    "Outdoor area, unattended parking — 1/40": 0.025,
}

MBQ_PER_MCI = 37.0  # exact-enough clinical convention (1 mCi = 37 MBq)


@dataclass
class Source:
    """The radioactive source in the room (a patient/vial of one radionuclide)."""
    isotope: str = "F-18"
    activity_MBq: float = 370.0        # per patient at the position
    patients_per_week: float = 40.0
    residence_min: float = 60.0        # minutes the source sits at this position per patient
    x_m: float = 2.0                   # position inside the room (SW origin)
    y_m: float = 2.0

    def activity_mCi(self) -> float:
        return self.activity_MBq / MBQ_PER_MCI

    def source_hours_per_week(self) -> float:
        """Total source-present hours per week at this position (the workload)."""
        return self.patients_per_week * self.residence_min / 60.0


@dataclass
class Room:
    """Rectangular room footprint (top view) and height."""
    width_m: float = 6.0    # x extent (W->E)
    length_m: float = 4.0   # y extent (S->N)
    height_m: float = 3.0


@dataclass
class Opening:
    """A door, viewing window, duct, or maze entrance in a wall.

    `center_along_wall_m` is measured from the wall's start corner (for N/S the
    West corner; for E/W the South corner). Doors/windows carry a lead-equivalent
    thickness; ducts carry an air-channel radius; a maze carries the L-shaped
    return-wall description (corner/maze scatter — handled by the dedicated
    corner surrogate, outside the analytical model).
    """
    kind: str = "door"                     # 'door' | 'window' | 'duct' | 'maze'
    center_along_wall_m: float = 1.0
    width_m: float = 1.0                   # opening width (for drawing / duct footprint)
    lead_equiv_mm: float = 0.0             # door / window lead equivalent
    radius_mm: float = 0.0                 # duct radius
    # maze-only fields (L-shaped entrance):
    ret_material: str = "concrete"         # return-wall material
    ret_thickness_mm: float = 150.0        # return-wall thickness
    corridor_m: float = 0.8                # corridor length behind the wall
    shadow_offset_m: float = 0.5           # lateral offset of the shadowed point


@dataclass
class AdjacentArea:
    """The occupied area on the far side of a wall (the thing we protect)."""
    name: str = "Adjacent area"
    occupancy_T: float = 1.0               # NCRP occupancy factor
    kind: str = "public"                   # 'controlled' | 'public'
    design_goal_P_mSv_wk: Optional[float] = None  # None -> framework default


@dataclass
class Wall:
    """One of the four room walls: its build-up, adjacent area, and openings."""
    id: str = "N"
    material1: str = "concrete"
    thickness1_mm: float = 150.0
    material2: Optional[str] = None
    thickness2_mm: float = 0.0
    adjacent: AdjacentArea = field(default_factory=AdjacentArea)
    openings: List[Opening] = field(default_factory=list)


@dataclass
class RoomDesign:
    """A complete room design — the single object the UI, engines and report share."""
    room: Room = field(default_factory=Room)
    source: Source = field(default_factory=Source)
    walls: List[Wall] = field(default_factory=list)
    framework: str = "NCRP"                 # 'NCRP' | 'IAEA_NRRC'
    notes: str = ""
    schema_version: str = "1.0"

    # ---- construction helpers ------------------------------------------------
    @staticmethod
    def default() -> "RoomDesign":
        """A sensible starting design: 4 concrete walls, public areas all round."""
        walls = [
            Wall(id=wid, adjacent=AdjacentArea(name=f"{WALL_NAMES[wid]} area"))
            for wid in WALL_IDS
        ]
        return RoomDesign(walls=walls)

    def wall(self, wid: str) -> Wall:
        for w in self.walls:
            if w.id == wid:
                return w
        raise KeyError(f"No wall '{wid}' in design.")

    # ---- (de)serialization ---------------------------------------------------
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent)

    @staticmethod
    def from_json(text: str) -> "RoomDesign":
        d = json.loads(text)
        room = Room(**d.get("room", {}))
        source = Source(**d.get("source", {}))
        walls = []
        for wd in d.get("walls", []):
            adj = AdjacentArea(**wd.get("adjacent", {}))
            ops = [Opening(**o) for o in wd.get("openings", [])]
            wd2 = {k: v for k, v in wd.items() if k not in ("adjacent", "openings")}
            walls.append(Wall(adjacent=adj, openings=ops, **wd2))
        return RoomDesign(
            room=room, source=source, walls=walls,
            framework=d.get("framework", "NCRP"),
            notes=d.get("notes", ""),
            schema_version=d.get("schema_version", "1.0"),
        )

    # ---- validation ----------------------------------------------------------
    def validate(self) -> List[str]:
        """Return a list of human-readable problems (empty = valid)."""
        errs: List[str] = []
        r = self.room
        if r.width_m <= 0 or r.length_m <= 0 or r.height_m <= 0:
            errs.append("Room dimensions must be positive.")
        s = self.source
        if not (0 <= s.x_m <= r.width_m and 0 <= s.y_m <= r.length_m):
            errs.append("Source position is outside the room footprint.")
        if s.isotope not in ISOTOPES:
            errs.append(f"Unknown isotope '{s.isotope}'.")
        if s.activity_MBq <= 0 or s.patients_per_week <= 0 or s.residence_min <= 0:
            errs.append("Activity, patients/week and residence time must be positive.")
        seen = set()
        for w in self.walls:
            if w.id in seen:
                errs.append(f"Duplicate wall '{w.id}'.")
            seen.add(w.id)
            if w.thickness1_mm < 0 or w.thickness2_mm < 0:
                errs.append(f"Wall {w.id}: negative thickness.")
            if w.adjacent.occupancy_T <= 0:
                errs.append(f"Wall {w.id}: occupancy factor must be > 0.")
            span = r.width_m if w.id in ("N", "S") else r.length_m
            for op in w.openings:
                half = op.width_m / 2.0
                if not (0 <= op.center_along_wall_m - half and
                        op.center_along_wall_m + half <= span + 1e-9):
                    errs.append(f"Wall {w.id}: opening '{op.kind}' does not fit on the wall.")
        return errs

"""
drawn_plan.py
=============
Reads a plan drawn in Room Designer (the free-hand drawing app embedded on the Draw & Survey page)
into metres: every wall side as a straight segment with its drawn thickness, the doors and windows
set into those sides, the radiation symbol as the source position, and the numbered survey points.

Room Designer stores positions in plan units and the scale as `settings.unitsPerMeter` (100 unless
the user set the scale, so 1 unit = 1 cm). A wall is a polyline; a closed one also joins its last
point to its first. A side's thickness is its own override when it has one, else the wall's, else
the plan's default. An opening sits on one side at fraction `t` from the side's first point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

Point = Tuple[float, float]

OPENING_NAMES = {"door": "Door", "door2": "Double door", "slider": "Sliding door",
                 "window": "Window", "leadglass": "Lead glass window", "gap": "Opening"}
DOOR_TYPES = ("door", "door2", "slider")


@dataclass(frozen=True)
class Segment:
    """One straight side of a drawn wall, in metres."""
    key: str                  # "W<wall>.<side>", 1-based, in drawing order
    wall_id: str              # Room Designer's id for the wall
    side: int                 # 0-based side index within the wall
    a: Point
    b: Point
    thickness_m: float
    outline: bool             # True for the room outline, False for an inner wall

    @property
    def length_m(self) -> float:
        return math.dist(self.a, self.b)

    @property
    def label(self) -> str:
        what = "Outline" if self.outline else "Inner wall"
        return f"{what} {self.key}, side {self.side + 1} ({self.length_m:.2f} m)"


@dataclass(frozen=True)
class PlanOpening:
    """A door, window or plain gap set into one side."""
    key: str                  # "O<n>", 1-based
    kind: str                 # Room Designer's type: door, door2, slider, window, leadglass, gap
    segment_key: str
    t: float                  # centre, as a fraction of the side from its first point
    width_m: float
    vision_panel: bool        # a door with a lead-glass viewing panel

    @property
    def label(self) -> str:
        panel = " with glass panel" if self.vision_panel else ""
        return f"{self.key} {OPENING_NAMES.get(self.kind, 'Opening')}{panel} on {self.segment_key}"


@dataclass(frozen=True)
class SurveyPoint:
    n: int
    label: str
    xy: Point


@dataclass(frozen=True)
class DrawnPlan:
    name: str
    segments: Tuple[Segment, ...]
    openings: Tuple[PlanOpening, ...]
    sources: Tuple[Point, ...]
    points: Tuple[SurveyPoint, ...]

    def segment(self, key: str) -> Segment:
        return next(s for s in self.segments if s.key == key)

    def problems(self) -> List[str]:
        """What stops a survey from being calculated, in the user's words (empty = ready)."""
        out = []
        if not self.segments:
            out.append("The plan has no walls. Draw the room outline first.")
        if not self.sources:
            out.append("Place the radiation symbol (Trefoil tool) where the source or patient sits.")
        if not self.points:
            out.append("Add survey points (Point tool, or 'Number every wall').")
        return out


def _side_thickness(wall: dict, side: int, default_units: float) -> float:
    override = (wall.get("segThickness") or {}).get(str(side))
    if override is None:
        override = (wall.get("segThickness") or {}).get(side)
    if override is not None:
        return float(override)
    return float(wall["thickness"]) if wall.get("thickness") is not None else default_units


def _segments(plan: dict, units_per_m: float) -> List[Segment]:
    default_units = float(plan["settings"].get("wallThickness", 14))
    out = []
    for number, wall in enumerate(plan.get("walls", []), start=1):
        points = [(p["x"] / units_per_m, p["y"] / units_per_m) for p in wall.get("points", [])]
        sides = len(points) if wall.get("closed") and len(points) > 2 else len(points) - 1
        for side in range(max(sides, 0)):
            a, b = points[side], points[(side + 1) % len(points)]
            if math.dist(a, b) <= 0.0:
                continue
            out.append(Segment(
                key=f"W{number}.{side + 1}", wall_id=wall["id"], side=side, a=a, b=b,
                thickness_m=_side_thickness(wall, side, default_units) / units_per_m,
                outline=wall.get("kind") == "outline"))
    return out


def _openings(plan: dict, segments: List[Segment], units_per_m: float) -> List[PlanOpening]:
    by_side = {(s.wall_id, s.side): s for s in segments}
    out = []
    for opening in plan.get("openings", []):
        segment = by_side.get((opening.get("pathId"), opening.get("seg")))
        if segment is None:
            continue                       # anchored to a wall that is no longer in the plan
        out.append(PlanOpening(
            key=f"O{len(out) + 1}", kind=opening.get("type", "gap"), segment_key=segment.key,
            t=float(opening.get("t", 0.5)), width_m=float(opening.get("width", 90)) / units_per_m,
            vision_panel=bool(opening.get("vision")) and opening.get("type") in DOOR_TYPES))
    return out


def _sources(plan: dict, units_per_m: float) -> List[Point]:
    return [(item["x"] / units_per_m, item["y"] / units_per_m) for item in plan.get("items", [])
            if item.get("type") == "trefoil" or item.get("trefoil")]


def parse_plan(plan: dict) -> DrawnPlan:
    """The plan in metres. Raises ValueError for something that is not a Room Designer plan."""
    if not isinstance(plan, dict) or "walls" not in plan or "settings" not in plan:
        raise ValueError("This is not a Room Designer plan (no walls or settings).")
    units_per_m = float(plan["settings"].get("unitsPerMeter") or 100.0)
    if units_per_m <= 0:
        raise ValueError("The plan's scale is not positive.")
    segments = _segments(plan, units_per_m)
    points = sorted((SurveyPoint(int(m["n"]), str(m.get("label") or ""),
                                 (m["x"] / units_per_m, m["y"] / units_per_m))
                     for m in plan.get("markers", [])), key=lambda p: p.n)
    return DrawnPlan(name=str(plan.get("name") or "Untitled room"), segments=tuple(segments),
                     openings=tuple(_openings(plan, segments, units_per_m)),
                     sources=tuple(_sources(plan, units_per_m)), points=tuple(points))


def nearest_segment(plan: DrawnPlan, xy: Point) -> Optional[Tuple[Segment, Point, float]]:
    """(segment, foot of the perpendicular, distance from its centre line) of the closest side."""
    best = None
    for segment in plan.segments:
        foot = _foot(segment.a, segment.b, xy)
        gap = math.dist(foot, xy)
        if best is None or gap < best[2]:
            best = (segment, foot, gap)
    return best


def _foot(a: Point, b: Point, p: Point) -> Point:
    """The closest point to `p` on the segment a-b."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)
    t = min(1.0, max(0.0, t))
    return (ax + t * dx, ay + t * dy)

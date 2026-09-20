"""
diagram.py
==========
Top-view schematic of the room that re-renders on every change: walls coloured by
their shielding status (green pass / red fail / grey undetermined / amber OOD
fallback), the source as a star, each point of protection as a triangle annotated
with its distance, and doors/windows/ducts drawn on their walls. Returns PNG bytes
so the same image is used in the Streamlit page and embedded in the report.
"""

from __future__ import annotations

import io
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Patch

from .model import RoomDesign
from .geometry import all_paths
from .engines import EngineResult

STATUS_COLOR = {
    "pass": "#21875B",
    "review": "#C27B00",
    "fail": "#C23B44",
    "none": "#9e9e9e",
    "ood": "#7A5A00",
}

# Colour is never the only carrier of a verdict. A barrier's status is also drawn
# into the stroke, so the plan survives greyscale printing into a submission
# binder and stays readable with a colour-vision deficiency. A failing wall gets a
# dense white dash struck over the solid stroke, which reads as hatching at this
# line weight; review is a long dash, not-evaluated a dot.
STATUS_OVERSTRIKE = {
    "fail": (0, (2, 2)),
    "review": (0, (7, 4)),
    "ood": (0, (7, 4)),
    "none": (0, (1, 3)),
}

# Legend equivalent of the overstrike above (see _status_handle for why the legend
# cannot reuse the line construction).
STATUS_LEGEND_HATCH = {
    "fail": "////",
    "review": "//",
    "ood": "//",
    "none": "..",
}


def _status(res: EngineResult, status_override: str | None = None) -> str:
    if status_override in STATUS_COLOR:
        return status_override
    if res is None:
        return "none"
    if res.ood:
        return "ood"
    if res.passes is True:
        return "pass"
    if res.passes is False:
        return "fail"
    return "none"


def _draw_walls(ax, design: RoomDesign, by_id: Dict, status_by_label: Dict) -> None:
    room = design.room
    segments = {
        "S": ((0, 0), (room.width_m, 0)),
        "N": ((0, room.length_m), (room.width_m, room.length_m)),
        "W": ((0, 0), (0, room.length_m)),
        "E": ((room.width_m, 0), (room.width_m, room.length_m)),
    }
    offsets = {
        "S": (0, -0.32),
        "N": (0, 0.32),
        "W": (-0.32, 0),
        "E": (0.32, 0),
    }
    for wall_id, ((x0, y0), (x1, y1)) in segments.items():
        wall_result = by_id.get(wall_id)
        status_override = (
            status_by_label.get(wall_result.label) if wall_result is not None else None
        )
        status = _status(wall_result, status_override)
        color = STATUS_COLOR[status]
        ax.plot(
            [x0, x1], [y0, y1], color=color, lw=7,
            solid_capstyle="butt", zorder=3,
        )
        overstrike = STATUS_OVERSTRIKE.get(status)
        if overstrike is not None:
            ax.plot(
                [x0, x1], [y0, y1], color="#ffffff", lw=3.2,
                linestyle=overstrike, solid_capstyle="butt", zorder=4,
            )
        midpoint_x, midpoint_y = (x0 + x1) / 2, (y0 + y1) / 2
        offset_x, offset_y = offsets[wall_id]
        ax.text(
            midpoint_x + offset_x, midpoint_y + offset_y, wall_id,
            ha="center", va="center", fontsize=11,
            fontweight="bold", color=color,
        )


def _draw_source(ax, design: RoomDesign) -> None:
    source = design.source
    ax.plot(
        source.x_m, source.y_m, marker="*", markersize=20,
        color="#d62728", zorder=6,
    )
    ax.text(
        source.x_m, source.y_m - 0.28,
        f"{source.isotope}\n{source.activity_MBq:g} MBq",
        ha="center", va="top", fontsize=8, color="#d62728",
    )


def _draw_opening(ax, design: RoomDesign, path, color: str) -> None:
    opening_x, opening_y = _opening_xy(design, path)
    if path.kind == "duct":
        ax.add_patch(
            Circle((opening_x, opening_y), 0.15, fc="white", ec=color, lw=2.5, zorder=5)
        )
        marker = ("D", 7)
    elif path.kind == "maze":
        ax.plot(
            opening_x, opening_y, marker="s", markersize=13,
            mfc="#ede7f6", mec=color, mew=2.5, zorder=5,
        )
        ax.plot(path.pop_xy[0], path.pop_xy[1], marker="^", markersize=8, color=color, zorder=6)
        marker = ("M", 7)
    else:
        face = "#b3e5fc" if path.kind == "window" else "#fff9c4"
        ax.plot(
            opening_x, opening_y, marker="s", markersize=12,
            mfc=face, mec=color, mew=2.5, zorder=5,
        )
        marker = ("W" if path.kind == "window" else "d", 6.5)
    ax.text(
        opening_x, opening_y, marker[0], ha="center", va="center",
        fontsize=marker[1], fontweight="bold", color=color, zorder=6,
    )


def _draw_paths(ax, design: RoomDesign, by_label: Dict, status_by_label: Dict) -> None:
    source = design.source
    for path in all_paths(design):
        point_x, point_y = path.pop_xy
        if path.kind == "wall":
            ax.plot(point_x, point_y, marker="^", markersize=9, color="#37474f", zorder=6)
            ax.plot(
                [source.x_m, point_x], [source.y_m, point_y],
                ls=":", lw=0.8, color="#90a4ae", zorder=2,
            )
            ax.text(
                point_x, point_y + 0.18, f"{path.d_pop_m:.1f} m",
                ha="center", va="bottom", fontsize=7, color="#37474f",
            )
            continue
        opening_result = by_label.get(path.label)
        color = STATUS_COLOR[
            _status(opening_result, status_by_label.get(path.label))
        ]
        _draw_opening(ax, design, path, color)


def _draw_dimensions(ax, room, pad: float) -> None:
    ax.annotate(
        "", xy=(0, -pad * 0.55), xytext=(room.width_m, -pad * 0.55),
        arrowprops=dict(arrowstyle="<->", color="#607d8b", lw=0.8),
    )
    ax.text(
        room.width_m / 2, -pad * 0.7, f"{room.width_m:g} m",
        ha="center", va="top", fontsize=8, color="#607d8b",
    )
    ax.annotate(
        "", xy=(-pad * 0.55, 0), xytext=(-pad * 0.55, room.length_m),
        arrowprops=dict(arrowstyle="<->", color="#607d8b", lw=0.8),
    )
    ax.text(
        -pad * 0.7, room.length_m / 2, f"{room.length_m:g} m",
        ha="right", va="center", rotation=90, fontsize=8, color="#607d8b",
    )


def _status_handle(status: str, label: str) -> Patch:
    """Legend swatch carrying the status by hatch density as well as by colour.

    The swatch is a hatched patch rather than an overstruck line: a legend entry
    scales its handle to a short swatch, which collapses a dash pattern to nothing,
    so the same two-line construction used on the walls would read as solid here.
    Hatch density mirrors the overstrike -- dense for a failure, open for review.
    """
    return Patch(
        facecolor=STATUS_COLOR[status],
        edgecolor="#ffffff",
        hatch=STATUS_LEGEND_HATCH.get(status),
        linewidth=0,
        label=label,
    )


def _add_legend(ax) -> None:
    handles = [
        _status_handle("pass", "Pass"),
        _status_handle("review", "Review"),
        _status_handle("fail", "Fail"),
        _status_handle("none", "Not evaluated"),
    ]
    ax.legend(
        handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.02),
        ncol=4, frameon=False, fontsize=8,
        handlelength=2.6, handleheight=1.1,
    )


def render(
    design: RoomDesign,
    results: List[EngineResult],
    status_by_label: Dict[str, str] | None = None,
) -> bytes:
    """Render the room plan with optional presentation-level status overrides."""
    room = design.room
    status_by_label = status_by_label or {}
    wall_results = {
        result.label.split()[1]: result
        for result in results
        if result.label.startswith("Wall ") and "·" not in result.label
    }
    results_by_label = {result.label: result for result in results}

    figure, axes = plt.subplots(figsize=(6.2, 5.0))
    pad = max(room.width_m, room.length_m) * 0.28 + 0.5
    axes.set_xlim(-pad, room.width_m + pad)
    axes.set_ylim(-pad, room.length_m + pad)
    axes.set_aspect("equal")
    axes.axis("off")
    axes.add_patch(
        Rectangle((0, 0), room.width_m, room.length_m, fc="#f5f7fa", ec="none", zorder=0)
    )
    _draw_walls(axes, design, wall_results, status_by_label)
    _draw_source(axes, design)
    _draw_paths(axes, design, results_by_label, status_by_label)
    _draw_dimensions(axes, room, pad)
    _add_legend(axes)

    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=140, bbox_inches="tight")
    plt.close(figure)
    return buffer.getvalue()

def _opening_xy(design: RoomDesign, path) -> tuple:
    """Coordinates of an opening marker on its wall."""
    r = design.room
    wid = path.wall_id
    # recover the along-position from the POP (which shares the along coordinate)
    px, py = path.pop_xy
    if wid == "N":
        return (px, r.length_m)
    if wid == "S":
        return (px, 0.0)
    if wid == "E":
        return (r.width_m, py)
    return (0.0, py)  # W

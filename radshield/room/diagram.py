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
from matplotlib.patches import Rectangle, Circle

from .model import RoomDesign
from .geometry import all_paths
from .engines import EngineResult

STATUS_COLOR = {
    "pass": "#2e7d32",
    "fail": "#c62828",
    "none": "#9e9e9e",
    "ood": "#f9a825",
}


def _status(res: EngineResult) -> str:
    if res is None:
        return "none"
    if res.ood:
        return "ood"
    if res.passes is True:
        return "pass"
    if res.passes is False:
        return "fail"
    return "none"


def render(design: RoomDesign, results: List[EngineResult]) -> bytes:
    r = design.room
    by_id: Dict[str, EngineResult] = {}
    for res in results:
        # keep the wall result (not the opening) for wall colouring
        if res.label.startswith("Wall ") and "·" not in res.label:
            by_id[res.label.split()[1]] = res

    by_label = {res.label: res for res in results}    # for colouring openings by status

    fig, ax = plt.subplots(figsize=(6.2, 5.0))
    pad = max(r.width_m, r.length_m) * 0.28 + 0.5
    ax.set_xlim(-pad, r.width_m + pad)
    ax.set_ylim(-pad, r.length_m + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    # room fill
    ax.add_patch(Rectangle((0, 0), r.width_m, r.length_m, fc="#f5f7fa", ec="none", zorder=0))

    # wall segments (drawn thick, coloured by status)
    seg = {
        "S": ((0, 0), (r.width_m, 0)),
        "N": ((0, r.length_m), (r.width_m, r.length_m)),
        "W": ((0, 0), (0, r.length_m)),
        "E": ((r.width_m, 0), (r.width_m, r.length_m)),
    }
    for wid, ((x0, y0), (x1, y1)) in seg.items():
        col = STATUS_COLOR[_status(by_id.get(wid))]
        ax.plot([x0, x1], [y0, y1], color=col, lw=7, solid_capstyle="butt", zorder=3)
        # wall label
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        off = {"S": (0, -0.32), "N": (0, 0.32), "W": (-0.32, 0), "E": (0.32, 0)}[wid]
        ax.text(mx + off[0], my + off[1], wid, ha="center", va="center",
                fontsize=11, fontweight="bold", color=col)

    # source star + label
    s = design.source
    ax.plot(s.x_m, s.y_m, marker="*", markersize=20, color="#d62728", zorder=6)
    ax.text(s.x_m, s.y_m - 0.28, f"{s.isotope}\n{s.activity_MBq:g} MBq",
            ha="center", va="top", fontsize=8, color="#d62728")

    # points of protection + distance annotations + openings
    for p in all_paths(design):
        px, py = p.pop_xy
        if p.kind == "wall":
            ax.plot(px, py, marker="^", markersize=9, color="#37474f", zorder=6)
            ax.plot([s.x_m, px], [s.y_m, py], ls=":", lw=0.8, color="#90a4ae", zorder=2)
            ax.text(px, py + 0.18, f"{p.d_pop_m:.1f} m", ha="center", va="bottom",
                    fontsize=7, color="#37474f")
        else:
            # opening marker ON the wall, outlined by its pass/fail status
            ox, oy = _opening_xy(design, p)
            oc = STATUS_COLOR[_status(by_label.get(p.label))]
            if p.kind == "duct":
                ax.add_patch(Circle((ox, oy), 0.15, fc="white", ec=oc, lw=2.5, zorder=5))
                ax.text(ox, oy, "D", ha="center", va="center", fontsize=7,
                        fontweight="bold", color=oc, zorder=6)
            elif p.kind == "maze":
                ax.plot(ox, oy, marker="s", markersize=13, mfc="#ede7f6", mec=oc,
                        mew=2.5, zorder=5)
                ax.text(ox, oy, "M", ha="center", va="center", fontsize=7,
                        fontweight="bold", color=oc, zorder=6)
                # shadowed point marker at the maze POP
                ax.plot(p.pop_xy[0], p.pop_xy[1], marker="^", markersize=8,
                        color=oc, zorder=6)
            else:  # window or door: square, filled pale, edged by status
                face = "#b3e5fc" if p.kind == "window" else "#fff9c4"
                ax.plot(ox, oy, marker="s", markersize=12, mfc=face, mec=oc,
                        mew=2.5, zorder=5)
                ax.text(ox, oy, "W" if p.kind == "window" else "d", ha="center",
                        va="center", fontsize=6.5, color=oc, zorder=6)

    # dimension annotations
    ax.annotate("", xy=(0, -pad * 0.55), xytext=(r.width_m, -pad * 0.55),
                arrowprops=dict(arrowstyle="<->", color="#607d8b", lw=0.8))
    ax.text(r.width_m / 2, -pad * 0.7, f"{r.width_m:g} m", ha="center", va="top",
            fontsize=8, color="#607d8b")
    ax.annotate("", xy=(-pad * 0.55, 0), xytext=(-pad * 0.55, r.length_m),
                arrowprops=dict(arrowstyle="<->", color="#607d8b", lw=0.8))
    ax.text(-pad * 0.7, r.length_m / 2, f"{r.length_m:g} m", ha="right", va="center",
            rotation=90, fontsize=8, color="#607d8b")

    # legend
    handles = [
        plt.Line2D([], [], color=STATUS_COLOR["pass"], lw=7, label="pass"),
        plt.Line2D([], [], color=STATUS_COLOR["fail"], lw=7, label="fail"),
        plt.Line2D([], [], color=STATUS_COLOR["ood"], lw=7, label="OOD fallback"),
        plt.Line2D([], [], color=STATUS_COLOR["none"], lw=7, label="undetermined"),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.02),
              ncol=4, frameon=False, fontsize=8)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


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

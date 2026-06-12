"""
limits.py
=========
Turns a regulatory framework choice into a numeric DESIGN GOAL P (the maximum
acceptable dose behind the barrier) and renders the pass/fail VERDICT.

Two frameworks (from data/limits.json), selectable per project:

  * 'NCRP'      -> weekly air-kerma design goals
                   (0.1 mGy/wk controlled, 0.02 mGy/wk uncontrolled).
  * 'IAEA_NRRC' -> annual dose constraints (default 6 mSv/y controlled,
                   0.3 mSv/y uncontrolled) divided by weeks/year, matching the
                   Saudi NRRC-R-01 / IAEA GSR Part 3 limit basis.

The design goal is compared with (transmitted dose / occupancy-adjusted goal):
a barrier is acceptable if  K_behind <= P / T  (NCRP convention), equivalently if
the transmitted dose at the point, including occupancy, is at or below P.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .. import data_loader as dl


@dataclass
class DesignGoal:
    """The numeric goal used for the verdict, plus how it was derived."""
    P_weekly: float          # design goal per week, in `unit`
    unit: str                # 'mGy/week' (NCRP air kerma) or 'mSv/week'
    area_type: str           # 'controlled' or 'uncontrolled'
    framework: str
    occupancy_T: float
    basis: str               # human-readable derivation
    refs: list


def design_goal(framework: str, area_type: str, occupancy_T: float = 1.0,
                override_P_weekly: Optional[float] = None) -> DesignGoal:
    """Build the DesignGoal for a framework + area type.

    Parameters
    ----------
    framework   : 'NCRP' or 'IAEA_NRRC'.
    area_type   : 'controlled' or 'uncontrolled'.
    occupancy_T : occupancy factor of the area (NCRP Table 4.1); default 1.
    override_P_weekly : if given, use this weekly goal directly (the UI lets the
                        user override the value; all defaults are editable).
    """
    data = dl.limits()["frameworks"]
    if framework not in data:
        raise ValueError(f"Unknown framework '{framework}'. Options: {list(data)}")
    fw = data[framework]

    if framework == "NCRP":
        block = fw[area_type]
        P = override_P_weekly if override_P_weekly is not None else block["P_weekly"]
        return DesignGoal(
            P_weekly=P, unit=block["unit_weekly"], area_type=area_type,
            framework=framework, occupancy_T=occupancy_T,
            basis=f"NCRP weekly air-kerma design goal for {area_type} area "
                  f"= {block['P_weekly']} {block['unit_weekly']}.",
            refs=[block.get("ref", "NCRP147")],
        )

    # IAEA / NRRC annual constraint -> weekly
    dc = fw["design_constraints_default"]
    weeks = dc["weeks_per_year"]
    annual = dc["controlled_mSv_per_y"] if area_type == "controlled" else dc["uncontrolled_mSv_per_y"]
    P = override_P_weekly if override_P_weekly is not None else annual / weeks
    return DesignGoal(
        P_weekly=P, unit="mSv/week", area_type=area_type,
        framework=framework, occupancy_T=occupancy_T,
        basis=f"IAEA/NRRC annual dose constraint for {area_type} area "
              f"= {annual} mSv/y / {weeks} wk = {annual/weeks:.4g} mSv/wk.",
        refs=dc.get("ref", ["SRS47", "NRRC_R01"]),
    )


@dataclass
class Verdict:
    """Result of comparing a transmitted dose with the design goal."""
    transmitted: float       # dose behind the barrier at the point (per week)
    goal_over_T: float       # P / T (the level the transmitted dose must not exceed)
    acceptable: bool
    margin_ratio: float      # goal_over_T / transmitted  (>=1 is a pass; headroom)
    unit: str
    message: str


def verdict(transmitted_dose: float, goal: DesignGoal) -> Verdict:
    """Acceptable if transmitted_dose <= P / T.

    The occupancy factor T allows a partially-occupied area to receive a higher
    average dose by 1/T (NCRP 147 Section 4.1.3). margin_ratio > 1 means there is
    headroom; < 1 means the barrier is insufficient.
    """
    goal_over_T = goal.P_weekly / goal.occupancy_T if goal.occupancy_T > 0 else goal.P_weekly
    acceptable = transmitted_dose <= goal_over_T
    margin = (goal_over_T / transmitted_dose) if transmitted_dose > 0 else float("inf")
    if acceptable:
        msg = (f"ACCEPTABLE: transmitted {transmitted_dose:.3g} {goal.unit} "
               f"<= goal/T {goal_over_T:.3g} {goal.unit} "
               f"(headroom x{margin:.2f}).")
    else:
        msg = (f"NOT ACCEPTABLE: transmitted {transmitted_dose:.3g} {goal.unit} "
               f"exceeds goal/T {goal_over_T:.3g} {goal.unit} "
               f"by x{1/margin:.2f}. Add shielding.")
    return Verdict(transmitted_dose, goal_over_T, acceptable, margin, goal.unit, msg)

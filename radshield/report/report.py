"""
report.py
=========
Builds a self-contained HTML report of a shielding calculation: every input,
the per-component results, the verdict, the required/preferred thicknesses, the
barrier's equivalents, and the full list of references used. The HTML can be
opened in any browser and printed to PDF (Ctrl+P) - no extra libraries needed.

The report is the auditable record the RSO keeps for the design file.
"""

from __future__ import annotations

import datetime
import html
from typing import List

from .. import data_loader as dl


def _row(cells, tag="td"):
    return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"


def build_html(*, source, barrier, goal, evaluation,
               inputs: dict, prepared_by: str = "Abdelaziz Habib",
               facility: str = "") -> str:
    """Return a complete HTML document string for the calculation.

    Parameters
    ----------
    source     : the SourceTerm used.
    barrier    : the Barrier evaluated.
    goal       : the DesignGoal.
    evaluation : the Evaluation result from solver.evaluate().
    inputs     : a dict of the raw user inputs (for the record).
    prepared_by, facility : header fields.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    verdict = evaluation.verdict
    verdict_color = "#1a7f37" if verdict.acceptable else "#cf222e"
    verdict_word = "ACCEPTABLE" if verdict.acceptable else "NOT ACCEPTABLE"

    # input rows
    input_rows = "".join(_row([html.escape(str(k)), html.escape(str(v))])
                         for k, v in inputs.items())

    # component rows
    comp_rows = "".join(
        _row([html.escape(cr.name), f"{cr.unshielded:.4g}", f"{cr.transmission:.4g}",
              f"{cr.transmitted:.4g}", html.escape(cr.detail)])
        for cr in evaluation.components
    )

    # equivalents
    eq = "; ".join(f"{v:.2f} mm {k}" for k, v in evaluation.equivalents.items()) or "n/a"

    # references actually used by this calculation
    ref_keys = list(dict.fromkeys((source.refs or []) + (goal.refs or [])))
    ref_items = "".join(f"<li><b>{html.escape(k)}</b>: {html.escape(dl.citation(k))}</li>"
                        for k in ref_keys)

    notes = "".join(f"<li>{html.escape(n)}</li>" for n in evaluation.notes)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>ShieldLab Report</title>
<style>
  body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #1c1c1c; }}
  h1 {{ font-size: 22px; margin-bottom: 0; }}
  h2 {{ font-size: 16px; border-bottom: 2px solid #ddd; padding-bottom: 4px; margin-top: 26px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 6px; }}
  th, td {{ border: 1px solid #ccc; padding: 5px 8px; text-align: left; vertical-align: top; }}
  th {{ background: #f0f3f6; }}
  .verdict {{ font-size: 18px; font-weight: bold; color: {verdict_color};
             border: 2px solid {verdict_color}; padding: 10px 14px; border-radius: 6px;
             display: inline-block; margin-top: 8px; }}
  .muted {{ color: #555; font-size: 12px; }}
  .small {{ font-size: 12px; }}
</style></head><body>

<h1>ShieldLab — Shielding Calculation Report</h1>
<p class="muted">Prepared by <b>{html.escape(prepared_by)}</b>{(' — ' + html.escape(facility)) if facility else ''}
 &nbsp;•&nbsp; Generated {now} &nbsp;•&nbsp; Method: standard analytical formalism (Archer / TVL / inverse-square)</p>

<div class="verdict">{verdict_word}</div>
<p class="small">{html.escape(verdict.message)}</p>

<h2>1. Inputs</h2>
<table><tr><th>Parameter</th><th>Value</th></tr>{input_rows}</table>

<h2>2. Design goal</h2>
<table>
  <tr><th>Framework</th><td>{html.escape(goal.framework)}</td></tr>
  <tr><th>Area type</th><td>{html.escape(goal.area_type)}</td></tr>
  <tr><th>Design goal P</th><td>{goal.P_weekly:.5g} {html.escape(goal.unit)}</td></tr>
  <tr><th>Occupancy factor T</th><td>{goal.occupancy_T:g}</td></tr>
  <tr><th>Goal / T (limit)</th><td>{goal.P_weekly/goal.occupancy_T:.5g} {html.escape(goal.unit)}</td></tr>
  <tr><th>Basis</th><td>{html.escape(goal.basis)}</td></tr>
</table>

<h2>3. Barrier</h2>
<p><b>{html.escape(barrier.describe())}</b> &nbsp; (areal weight ≈ {barrier.areal_density_kg_m2():.0f} kg/m²;
 total {barrier.total_thickness_mm():.0f} mm)</p>
<p class="small">Equivalent single-material thickness: {html.escape(eq)}</p>

<h2>4. Results (unshielded → transmission B → transmitted)</h2>
<table>
  <tr><th>Component</th><th>Unshielded ({html.escape(source.unit)})</th><th>Transmission B</th>
      <th>Transmitted ({html.escape(source.unit)})</th><th>How computed</th></tr>
  {comp_rows}
  <tr><th>TOTAL</th><th></th><th></th><th>{evaluation.transmitted_total:.4g}</th><th></th></tr>
  <tr><td>Scattered + leakage (secondary)</td><td></td><td></td>
      <td>{evaluation.transmitted_secondary:.4g}</td><td>the &quot;scattered radiation after this combination&quot;</td></tr>
</table>

<h2>5. Notes</h2>
<ul class="small">{notes or '<li>(none)</li>'}</ul>

<h2>6. References used</h2>
<ul class="small">{ref_items}</ul>

<p class="muted">ShieldLab v1.0 — planning/verification tool. A qualified expert must
review any design used for construction. Photons only; LINAC &gt; 10 MV neutron design out of scope.</p>
</body></html>"""

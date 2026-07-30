"""
report.py
=========
 Builds HTML and one-page PDF reports of a shielding calculation: every input,
the per-component results, the verdict, the required/preferred thicknesses, the
barrier's equivalents, and the full list of references used. The HTML can be
 opened in any browser and printed to PDF (Ctrl+P). The PDF summary uses fpdf2,
 which is already bundled for the Room Designer report export.

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


def build_pdf_summary(*, source, barrier, goal, evaluation, inputs: dict,
                      prepared_by: str = "Abdelaziz Habib", facility: str = "") -> bytes:
    """Return a clean, one-page decision summary for the core calculator."""
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    margin = evaluation.verdict.margin_ratio
    status = "PASS" if evaluation.verdict.acceptable else "FAIL"
    if evaluation.verdict.acceptable and margin < 1.20:
        status = "MARGINAL"
    colors = {"PASS": (31, 122, 61), "FAIL": (190, 45, 45), "MARGINAL": (185, 122, 0)}
    red, green, blue = colors[status]
    limit = goal.P_weekly / goal.occupancy_T

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "ShieldLab | Shielding Decision Summary", ln=1)
    pdf.set_font("Helvetica", "", 8.5)
    identity = f"Prepared by {prepared_by}" + (f" | {facility}" if facility else "")
    pdf.set_text_color(85, 85, 85)
    pdf.cell(0, 5, identity, ln=1)
    pdf.cell(0, 5, f"Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=1)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    pdf.set_fill_color(red, green, blue)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 14, status, fill=True, align="C", ln=1)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, evaluation.verdict.message.replace("≤", "<="), align="C")
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Calculated result", ln=1)
    pdf.set_font("Helvetica", "", 9)
    values = [
        ("Transmitted total", f"{evaluation.transmitted_total:.4g} {source.unit}"),
        ("Regulatory design goal / T", f"{limit:.4g} {source.unit}"),
        ("Safety margin", f"{margin:.2f}x"),
        ("AI 95% confidence interval", "Not applicable - analytical calculation"),
    ]
    pdf.set_fill_color(245, 247, 250)
    for label, value in values:
        pdf.cell(60, 7, label, border=1, fill=True)
        pdf.cell(0, 7, value, border=1, ln=1)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Calculation inputs", ln=1)
    input_items = list(inputs.items())
    for index in range(0, len(input_items), 2):
        for key, value in input_items[index:index + 2]:
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.cell(38, 5, str(key)[:23] + ":")
            pdf.set_font("Helvetica", "", 8.5)
            pdf.cell(57, 5, str(value)[:35])
        pdf.ln(5)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Barrier and dose breakdown", ln=1)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.multi_cell(0, 5, f"Barrier: {barrier.describe()}")
    headers = [("Component", 55), ("Unshielded", 34), ("B", 26), ("Transmitted", 38), ("Method", 37)]
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_fill_color(48, 84, 150)
    pdf.set_text_color(255, 255, 255)
    for label, width in headers:
        pdf.cell(width, 5.5, label, border=1, fill=True, align="C")
    pdf.ln(5.5)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 7.5)
    for component in evaluation.components[:8]:
        pdf.cell(55, 5.5, component.name[:27], border=1)
        pdf.cell(34, 5.5, f"{component.unshielded:.3g}", border=1, align="C")
        pdf.cell(26, 5.5, f"{component.transmission:.3g}", border=1, align="C")
        pdf.cell(38, 5.5, f"{component.transmitted:.3g}", border=1, align="C")
        pdf.cell(37, 5.5, component.detail[:18], border=1)
        pdf.ln(5.5)

    pdf.set_y(278)
    pdf.set_font("Helvetica", "I", 6.5)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 3, "Decision-support output. Requires review and sign-off by a qualified Radiation Safety Officer or medical physicist.")
    return bytes(pdf.output())

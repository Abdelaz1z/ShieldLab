"""
report_regulatory.py
====================
Formal REGULATORY SUBMISSION document for a shielding design — the artefact an RSO or
qualified expert hands to the regulator (Saudi NRRC / IAEA GSR Part 3 basis, or NCRP),
as opposed to `report_room.py`'s working results sheet.

It deliberately does NOT recompute anything: it consumes the dict that
`report_room.build_report()` already produced (so every number is identical to what the
app displayed) and wraps it in the structure a submission needs — identification,
regulatory basis, assumptions, method with citations, per-barrier compliance table,
findings, limitations, an optional cost/structural-load appendix, and a signature block.

Output is a self-contained printable HTML document (print to PDF from the browser),
which keeps fonts, tables and the plan-view image intact without a PDF font dependency.
"""

from __future__ import annotations

import base64
import html
from typing import Dict, Optional

from .. import data_loader as dl
from . import engines as eng

# References cited by the method section (resolved through data_loader so the wording
# always matches the app's own bibliography).
_METHOD_REFS = ["NCRP147", "NCRP151", "TG108", "OUMANO2025", "SRS47", "IAEA_BSS"]


def _esc(x) -> str:
    return html.escape("" if x is None else str(x))


def _rows_table(rows, units: Dict[str, str]) -> str:
    dose_unit = _esc(units.get("dose", "mSv/week"))
    goal_unit = _esc(units.get("goal", "mSv/week"))
    head = (
        "<tr><th>Barrier</th><th>Material</th><th>Thickness (mm)</th>"
        f"<th>Dose ({dose_unit})</th><th>Limit P/T ({goal_unit})</th><th>Margin</th>"
        "<th>Method tier</th><th>Verdict</th></tr>"
    )
    body = ""
    for r in rows:
        v = r.get("verdict", "—")
        display_verdict = "REVIEW REQUIRED" if v in ("MARGINAL", "REVIEW") else v
        colour = {
            "PASS": "#1b5e20",
            "FAIL": "#b71c1c",
            "REVIEW": "#8a5a00",
        }.get(v, "#8a6d1b")
        thick = r.get("suggested_mm") if r.get("suggested_mm") not in (None, "—") else "as declared"
        body += (
            f"<tr><td class='l'>{_esc(r.get('barrier'))}</td>"
            f"<td>{_esc(r.get('material'))}</td><td>{_esc(thick)}</td>"
            f"<td>{_esc(r.get('dose_mSv_wk'))}</td><td>{_esc(r.get('limit_weekly'))}</td>"
            f"<td>{_esc(r.get('margin'))}</td><td>{_esc(r.get('tier'))}</td>"
            f"<td style='color:{colour};font-weight:700'>{_esc(display_verdict)}</td></tr>")
    return f"<table>{head}{body}</table>"


def _cost_appendix(costs: Optional[Dict]) -> str:
    if not costs or not costs.get("priced_walls"):
        return ""
    body = ""
    for w in costs["walls"]:
        cur = w.current
        if cur is None:
            continue
        body += (f"<tr><td class='l'>{_esc(w.label)}</td><td>{w.area_m2:.1f}</td>"
                 f"<td>{cur.preferred_mm:g} mm {_esc(cur.material)}</td>"
                 f"<td>{w.cost_of(cur):,.0f}</td><td>{w.weight_of(cur):,.0f}</td></tr>")
    return f"""
<h2>Appendix A — Indicative cost and structural load</h2>
<p>Provided for construction planning and structural coordination. Costs are
representative planning estimates (materials plus labour) and are <b>not a quotation</b>;
the areal loads must be confirmed by the project structural engineer.</p>
<table><tr><th>Barrier</th><th>Area (m²)</th><th>Build</th>
<th>Indicative cost (USD)</th><th>Areal load (kg)</th></tr>{body}
<tr class='tot'><td class='l'><b>Total</b></td><td>—</td><td>—</td>
<td><b>{costs['total_current_usd']:,.0f}</b></td>
<td><b>{costs['total_current_weight_kg']:,.0f}</b></td></tr></table>"""


def build_submission_html(report: Dict, meta: Dict,
                          costs: Optional[Dict] = None) -> bytes:
    """Render the formal submission document.

    `report` : the dict from report_room.build_report() (numbers are reused verbatim).
    `meta`   : facility / licence / personnel fields collected in the UI.
    `costs`  : optional dict from shieldlab.room.cost.room_costs() -> Appendix A.
    """
    s = report.get("summary", {}) or {}
    status = s.get("status", "—")
    status_label = (
        "REVIEW REQUIRED" if status in ("MARGINAL", "REVIEW") else status
    )
    colour = {
        "PASS": "#1b5e20",
        "FAIL": "#b71c1c",
        "MARGINAL": "#8a5a00",
        "REVIEW": "#8a5a00",
    }.get(status, "#333")
    units = report.get("units") or {
        "dose": "mSv/week",
        "goal": "mSv/week",
    }

    inputs_html = "".join(
        f"<tr><td class='l'>{_esc(k)}</td><td>{_esc(v)}</td></tr>"
        for k, v in (report.get("inputs") or {}).items())

    refs_html = "".join(f"<li>{_esc(c)}</li>" for c in dl.citations(_METHOD_REFS)
                        if c not in _METHOD_REFS)  # drop keys that had no entry

    # Finite-field geometry bias is structured so it cannot disappear into a result footnote.
    biased_rows = [r for r in (report.get("rows") or []) if r.get("geometry_bias")]
    geometry_bias_html = ""
    if biased_rows:
        names = ", ".join(
            f"{_esc(r['barrier'])} (&mu;x&nbsp;&asymp;&nbsp;{r['mu_x']:.1f})"
            if isinstance(r.get("mu_x"), (int, float)) else _esc(r["barrier"])
            for r in biased_rows)
        geometry_bias_html = (
            f"<div class='band' style='border-color:#b71c1c'>"
            f"<b>Finite-beam caution — {names}.</b> "
            f"{_esc(eng.GEOMETRY_BIAS_WARNING)} The Monte-Carlo surrogate tier was trained on "
            f"transport through a finite 0.5&nbsp;m irradiated field; a dedicated convergence "
            f"study measured 0.5&nbsp;m to 1.5&nbsp;m increases of 1.58&times; and 1.73&times; at "
            f"&mu;x&nbsp;4 and 6 in concrete at 364&nbsp;keV; historical deep rows increased "
            f"1.8–2.0&times; at &mu;x&nbsp;8–12. The surrogate may therefore report transmission "
            f"<b>low</b>, the non-conservative direction. Other materials and energies remain "
            f"unquantified. The out-of-domain guard does not detect the condition (a barrier can "
            f"have ordinary features) and the analytical tier is not reliably the more conservative "
            f"option here, so the bias is disclosed rather than corrected."
            f"</div>")

    findings = report.get("failure_explanations") or []
    findings_html = ("".join(f"<li><b>{_esc(f['barrier'])}:</b> {_esc(f['message'])}</li>"
                             for f in findings)
                     if findings else "<li>No barrier failed its design goal in this assessment.</li>")

    if status == "PASS":
        declaration_html = (
            "<b>Declaration.</b> I confirm that the inputs above reflect the intended use of this "
            "room and that the shielding specified meets the stated design goals under the cited "
            "regulatory framework.")
    elif status in ("MARGINAL", "REVIEW"):
        declaration_html = (
            "<b>Declaration — review required.</b> I confirm that the inputs above reflect the intended use "
            "of this room. Approval remains pending because one or more paths require independent "
            "engineering or model-assurance review. This is not a declaration of compliance.")
    else:
        declaration_html = (
            f"<b>Declaration.</b> I confirm that the inputs above reflect the intended use of this "
            f"room. The overall assessment is <b>{_esc(status_label)}</b>: the shielding as "
            f"specified does <b>not</b> meet all stated design goals under the cited regulatory "
            f"framework (see sections 6 and 7). This submission documents the assessment and the "
            f"outstanding items; it is not a declaration of compliance.")

    diagram_html = ""
    if report.get("diagram_png"):
        b64 = base64.b64encode(report["diagram_png"]).decode("ascii")
        diagram_html = (f"<h2>4. Room layout (plan view)</h2>"
                        f"<img src='data:image/png;base64,{b64}' alt='Room plan view'/>")

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Radiation Shielding Design Submission — {_esc(meta.get('facility'))}</title>
<style>
 body{{font-family:Arial,Helvetica,sans-serif;color:#111;max-width:900px;margin:24px auto;
       padding:0 18px;line-height:1.5;font-size:13.5px}}
 h1{{font-size:21px;margin-bottom:2px}} h2{{font-size:16px;margin-top:26px;
       border-bottom:2px solid #305496;padding-bottom:3px;color:#204070}}
 table{{width:100%;border-collapse:collapse;margin:10px 0;font-size:12.5px}}
 th{{background:#305496;color:#fff;padding:6px 8px;text-align:center}}
 td{{padding:5px 8px;border-bottom:1px solid #d9dde3;text-align:center}}
 td.l{{text-align:left}} tr.tot td{{background:#eef2f8}}
 .band{{background:#f4f6f9;border-left:6px solid {colour};padding:10px 14px;margin:12px 0}}
 .sig{{margin-top:26px;border:1px solid #aab;padding:14px}}
 .sig div{{margin:20px 0 6px}} .muted{{color:#555;font-size:12px}}
 img{{max-width:100%;border:1px solid #ccd}}
 @media print{{body{{margin:0}} h2{{page-break-after:avoid}} table{{page-break-inside:avoid}}}}
</style></head><body>

<h1>Radiation Shielding Design — Regulatory Submission</h1>
<div class="muted">Generated by ShieldLab on {_esc(report.get('timestamp'))} ·
Document ref: {_esc(meta.get('doc_ref') or '—')} · Revision: {_esc(meta.get('revision') or '0')}</div>

<h2>1. Identification</h2>
<table>
 <tr><td class='l'>Facility</td><td class='l'>{_esc(meta.get('facility'))}</td></tr>
 <tr><td class='l'>Room / area assessed</td><td class='l'>{_esc(meta.get('room_ref'))}</td></tr>
 <tr><td class='l'>Licence / authorisation no.</td><td class='l'>{_esc(meta.get('licence'))}</td></tr>
 <tr><td class='l'>Prepared by</td><td class='l'>{_esc(meta.get('prepared_by'))}</td></tr>
 <tr><td class='l'>Reviewed / approved by</td><td class='l'>{_esc(meta.get('reviewed_by'))}</td></tr>
 <tr><td class='l'>Assessment mode</td><td class='l'>{_esc(report.get('mode'))}</td></tr>
</table>

<h2>2. Purpose, scope and regulatory basis</h2>
<p>This document presents the structural shielding assessment for the room identified above.
Design goals are derived under the <b>{_esc((report.get('inputs') or {}).get('Framework'))}</b>
framework: weekly air-kerma design goals for controlled and uncontrolled areas (NCRP), or the
annual dose constraints of IAEA GSR Part 3 as adopted by the Saudi NRRC, apportioned to a weekly
basis. The design goal applied to each barrier is the area's constraint <i>P</i> divided by its
occupancy factor <i>T</i>; both are listed per barrier in section 5 and were selected from the
NCRP occupancy table or entered explicitly.</p>
<div class="band"><b>Overall assessment: {_esc(status_label)}</b> — {_esc(s.get('message'))}</div>

<h2>3. Design assumptions and inputs</h2>
<table>{inputs_html}</table>
{diagram_html}

<h2>5. Method</h2>
<p>Two independent tiers are reported. The <b>analytical tier</b> applies the standard broad-beam
formalism (tenth-value-layer attenuation for radionuclide photons, inverse-square geometry and
occupancy weighting) prescribed by the references below. The <b>Monte-Carlo surrogate tier</b> is a
machine-learning model trained on analog Monte-Carlo transport (GATE / Geant4), reported with a
95&nbsp;% conformal prediction interval and an explicit out-of-domain guard; where a geometry falls
outside its validated domain the assessment falls back to the analytical tier and says so. Duct
penetrations and maze/corner paths are assessed by the surrogate tier because the analytical
broad-beam model carries no geometric term for them.</p>
<ul>{refs_html}</ul>

<h2>6. Barrier-by-barrier compliance</h2>
{_rows_table(report.get('rows') or [], units)}
<p class="muted">Dose is the calculated weekly dose at the point of protection (0.3 m beyond the
barrier); the limit is the area's design goal divided by its occupancy factor. Margin is the ratio
of limit to calculated dose; a value below 1 indicates non-compliance.
{_esc(report.get('unit_note'))}</p>

<h2>7. Findings</h2>
<ul>{findings_html}</ul>

<h2>8. Assumptions, limitations and exclusions</h2>
<p>{_esc(report.get('disclaimer'))}</p>
{geometry_bias_html}
<ul>
 <li>Photon shielding only; neutron production is not applicable at these photon energies.</li>
 <li>Occupancy factors and workload are the values stated in section 3 and must reflect the
     facility's actual practice; they are the responsibility of the licensee.</li>
 <li>Openings (doors, windows) are assessed by their stated lead equivalence, which must be
     confirmed against the supplier's certificate at the working energy.</li>
 <li>Skyshine and ground-scatter contributions are not assessed.</li>
 <li>This assessment supports, and does not replace, review and sign-off by a qualified expert.</li>
</ul>

{_cost_appendix(costs)}

<div class="sig">
 {declaration_html}
 <div>Prepared by: {_esc(meta.get('prepared_by'))} &nbsp;&nbsp; Signature: ______________________
 &nbsp;&nbsp; Date: __________</div>
 <div>Reviewed / approved by: {_esc(meta.get('reviewed_by'))} &nbsp;&nbsp;
 Signature: ______________________ &nbsp;&nbsp; Date: __________</div>
</div>

</body></html>"""
    return doc.encode("utf-8")

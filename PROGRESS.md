# ShieldLab — Project Progress Log

**Project:** Photon shielding design & verification software for medical radiation facilities
**Owner:** Radiation Safety Officer (KSA) — M.Sc. Radiation Protection, Cairo University
**Started:** 2026-06-10
**Status:** ✅ **ALL FOUR PARTS COMPLETE & INTEGRATED (v1.0).** 13/13 validation tests pass; all 5 modality groups render with 0 exceptions. Engine reproduces SRS 47 Co-60 (1034 mm vs 1033 mm) and RG 8.39 I-131 (4.53 mSv exact). Ready to run: `py -3.11 -m streamlit run app.py`.

---

## 1. Project goal

A well-organized, editable Python application (Streamlit web UI) that:

1. Lets the user pick a **modality** (radiography, fluoroscopy, mammography, CT, dental intraoral/panoramic/cephalometric, LINAC 4–18 MV, I-131/Lu-177 therapy ward, Tc-99m gamma camera, F-18 PET/CT) and the **maximum energy** (kVp / MV / radionuclide).
2. Takes the **distance** from the device (or patient-source) to each barrier and the **occupancy** of the area behind it.
3. Lets the user build a barrier from **mixed material layers** (lead, concrete, gypsum, steel, glass, wood, brick, … any material) with chosen thicknesses.
4. Reports the **transmitted primary and secondary (scatter + leakage) radiation** behind that combination, compares it with the selected **regulatory design goal**, gives a **pass/fail verdict**, and recommends the **required/preferred thicknesses**.
5. Cites the **reference for every number** used, and exports a full calculation report.

Method: **standard analytical formalism** (Archer broad-beam transmission, TVLs, inverse square, scatter fractions, buildup) — the formalism prescribed by NCRP 147 / NCRP 151 / IAEA SRS 47 / AAPM TG-108 and accepted by regulators. No Monte Carlo (per user decision 2026-06-10).

---

## 2. Decisions agreed with the user (2026-06-10)

| # | Question | Decision |
|---|----------|----------|
| 1 | Platform | **Python + Streamlit** web app (pure Python, editable, runs locally) |
| 2 | Scope | **All four groups**: diagnostic X-ray package (radiography, fluoro, mammo, CT, dental incl. panoramic), LINAC vault 4–18 MV, I-131 (+Lu-177) therapy room, NM imaging (Tc-99m + F-18 PET/CT) |
| 3 | Regulatory basis | **Selectable per project**: NCRP weekly design goals **and** IAEA/Saudi-NRRC annual dose constraints; all values editable with references shown |
| 4 | Physics method | **Standard analytical formalism** (no Monte Carlo) |

---

## 3. Research findings (Phase 0 — complete)

### 3.1 References provided by the user (in `References\`)

| File | Identified as | Use in model |
|------|--------------|--------------|
| `NCRP Report No. 147.pdf` (193 pp) | NCRP Report No. 147, *Structural Shielding Design for Medical X-Ray Imaging Facilities*, 2004 | **Core diagnostic methodology**: design goals P; occupancy factors T (Table 4.1); workload distributions per room type (AAPM TG-9 survey); unshielded primary/secondary air kerma per patient; CT DLP-based scatter (κ factors); Archer fit parameters α,β,γ for Pb, concrete, gypsum, steel, plate glass, wood at 25–35 kVp (Mo anode) and 50–150 kVp (W anode). Key tables located at PDF pages ≈82–101 (workloads/kermas) and ≈126–176 (fit parameters, appendices). |
| `NCRP_Report_172_AAPM.pdf` (144 pp) | NCRP Report No. 172, *Reference Levels and Achievable Doses in Medical and Dental Imaging*, 2012 | Context for realistic per-patient dose/workload defaults (DRLs). |
| `NDRL-En.pdf` (8 pp) | Saudi SFDA **MDS-G-008-V2** (26/10/2022), *National Diagnostic Reference Levels* | Saudi NDRLs (CT DLP values etc.) → KSA-specific default workloads/DLP; confirms Saudi regulatory context. |
| `RG 8.39.pdf` (24 pp) | US NRC **Regulatory Guide 8.39** (1997), *Release of Patients Administered Radioactive Materials* | I-131 patient-as-source **biokinetics**: occupancy factor 0.25 at 1 m, thyroidal/extrathyroidal uptake fractions and effective half-lives, dose-integration formalism → used for I-131 ward source term. |
| `RPII_Code_Design_Medical_Facilities_09.pdf` (112 pp) | RPII 09/01 (Ireland, June 2009), *The Design of Diagnostic Medical Facilities where Ionising Radiation is used* | European constraint-style design (0.3 mSv/y public dose constraint), room-design good practice. |
| `shielding height shb.pdf` (4 pp) | Excerpt, BIR *Radiation Shielding for Diagnostic Radiology* (Ch. 2) | **Barrier height & tertiary (ceiling/wall) scatter** method — scatter kerma per patient KAP (interventional) / per DLP (CT) vs barrier height and ceiling height; used for the barrier-height check the user specifically wants. |

### 3.2 References obtained by my own research

| Source | Status | Use in model |
|--------|--------|--------------|
| **IAEA Safety Reports Series No. 47**, *Radiation Protection in the Design of Radiotherapy Facilities*, IAEA, Vienna (2006), STI/PUB/1223 | ✅ Downloaded to `References\IAEA_SRS_47_Radiotherapy_Facilities.pdf` (official IAEA free PDF) | **LINAC vault methodology + data**: TVL₁/TVLₑ (concrete, steel, lead) for primary beams 4–18 MV; leakage TVLs; patient scatter fractions a(θ); use factors; maze/door guidance; Co-60 & HDR data. Cross-check against NCRP 151 values from literature. |
| **NCRP Report No. 151** (2005), *Structural Shielding Design and Evaluation for Megavoltage X- and Gamma-Ray Radiotherapy Facilities* | Methodology summarized from secondary literature (report not freely distributable). B_pri = P·d²/(W·U·T); leakage B_L = P·d²/(0.001·W_L); scatter fractions table at 10°–135° for 6–24 MV; IMRT factor C_I; TADR/IDR checks (≤20 µSv in-any-one-hour, NRC style); design goals identical to NCRP 147. | Equations + cross-validation of SRS 47 TVL data. |
| **Oumano M. et al.**, "Shielding resources for four common radiopharmaceuticals utilized for imaging and therapy: Tc-99m, F-18, I-131, and Lu-177", *J Appl Clin Med Phys* 2025;26(5):e70084, doi:10.1002/acm2.70084 (open access) | ✅ Verified online (PMC12059296) | **Archer α,β,γ fits for radionuclides** in lead & concrete (GATE/MCNP6 broad-beam MC): e.g. HVL/TVL Pb: Tc-99m 0.243/0.87 mm; I-131 2.48/10.5 mm; F-18 4.75/15.4 mm; Lu-177 0.511/1.99 mm. Concrete TVL: Tc-99m 122 mm; Lu-177 134 mm; I-131 186 mm; F-18 204 mm. Dose-rate constants given. → Nuclear-medicine transmission engine. |
| **AAPM Task Group 108 Report** (Madsen MT et al.), "PET and PET/CT Shielding Requirements", *Med Phys* 33(1), 2006 | ✅ Methodology confirmed; report freely accessible | PET patient-as-source method: uptake/imaging phases, decay during phases, patient self-attenuation (≈0.36 for F-18 at 511 keV), broad-beam transmission factors for lead/steel/concrete at 511 keV, worked examples for validation. |
| **NIST XCOM: Photon Cross Sections Database** (NBSIR 87-3597; Berger, Hubbell, Seltzer et al.), physics.nist.gov | ✅ Verified online | μ/ρ for **any element/compound/mixture, 1 keV–100 GeV** → generic material engine ("mix any other material") + material library (lead, ordinary/barite concrete, steel, gypsum, plate/lead glass, brick, wood, water…). |
| **ANSI/ANS-6.4.3-1991**, *Gamma-Ray Attenuation Coefficients and Buildup Factors for Engineering Materials* (G-P fitting coefficients, as republished in open literature) | Methodology confirmed | **Buildup factors** (Geometric-Progression form) for the generic mono-energetic broad-beam model used when no measured Archer/TVL fit exists for a material. |
| **IAEA GSR Part 3** (2014), *Radiation Protection and Safety of Radiation Sources: International Basic Safety Standards* | Well-established | Dose limits: occupational 20 mSv/y (avg 5 y, ≤50 mSv single year); public 1 mSv/y; lens/skin limits. Basis for IAEA/NRRC framework option. |
| **ICRP Publication 103** (2007) | Well-established | Underlying system of protection (justification/optimization/limits). |
| **Saudi NRRC** — Law of Nuclear and Radiological Control (Royal Decree M/81, 2018) + **Technical Regulation NRRC-R-01 (2022) "Radiation Safety"** (nrrc.gov.sa) | ⚠️ NRRC website unreachable from this machine (download blocked). KSA framework follows IAEA GSR Part 3 (20 mSv/y occ; 1 mSv/y public). | **ACTION (user):** if exact Saudi clause citations are wanted, place a copy of NRRC-R-01 in `References\`. Until then the IAEA GSR Part 3 values (which NRRC adopts) are used and labelled accordingly. |
| US NRC **10 CFR 20.1301** "in any one hour" public dose criterion (0.02 mSv/h) | Well-established | Optional TADR/IDR check for LINAC option. |

### 3.3 Key design-basis numbers collected (to be encoded with citations in Part 1)

- **NCRP design goals (NCRP 147 §1.4 / NCRP 151):** controlled P = 0.1 mGy air kerma/week (5 mGy/y); uncontrolled P = 0.02 mGy/wk (1 mGy/y). Point of protection 0.3 m beyond barrier.
- **IAEA/European constraint style (SRS 47, RPII 09/01):** annual constraint typically 6 mSv/y controlled-area workers; 0.3 mSv/y (sometimes up to 1 mSv/y) public — selectable + editable in the app.
- **Archer transmission model:** B(x) = [(1+β/α)·e^(α·γ·x) − β/α]^(−1/γ) — diagnostic kVp and radionuclide fits.
- **TVL model (megavoltage):** n = x₁/TVL₁ + (x−x₁)/TVLₑ; B = 10⁻ⁿ; example SRS-47/NCRP-151-class values: 6 MV concrete TVL₁≈37 cm, TVLₑ≈33 cm; 10 MV concrete 41/37 cm; 15 MV 44/41 cm; 18 MV 45/43 cm; lead 10 MV 57/57 mm; steel 10 MV 110/110 mm (final encoded values will be taken table-by-table from SRS 47 PDF with page citations).
- **LINAC secondary:** head leakage 0.1% of useful beam at 1 m; patient scatter fraction a(θ) per 400 cm² field; IMRT factor C_I (typ. 2–5) on leakage workload.
- **CT scatter (NCRP 147 §5; BIR):** κ·DLP scatter-kerma method + ceiling-height tertiary scatter factors (BIR Ch. 2 excerpt).
- **I-131 (RG 8.39):** dose-rate-constant Γ ≈ 2.2 R·cm²/(mCi·h) class value (exact value + SI conversion encoded with citation); retained activity = extrathyroidal fraction (T_eff ≈ 0.32 d) + thyroidal fraction (T_eff ≈ 5.2–7.3 d depending on condition); occupancy factor E=0.25 beyond ~1 m.
- **Photoneutron caveat:** for LINAC > 10 MV the model covers photons only and must display a mandatory warning + door/maze guidance note (stated limitation).

### 3.4 Validation targets (Part 4)

Reproduce, as automated tests, the worked examples in: NCRP 147 (Appendix examples), IAEA SRS 47 (sample 6/18 MV barrier calculations), AAPM TG-108 (sample PET wall), RG 8.39 (released-patient dose tables) — agreement within engineering tolerance (±5–10 %).

---

## 4. Architecture & build plan (four parts, as requested)

**Working name:** `ShieldLab` (folder `radshield/`)

```
Control Claude Program/
├── PROGRESS.md                ← this file (kept updated)
├── README.md                  ← install & user guide (Part 4)
├── requirements.txt
├── app.py                     ← Streamlit entry point
├── radshield/                 ← editable Python package
│   ├── data/                  ← PART 1: all datasets as human-readable JSON + reference keys
│   │   ├── materials.json         (densities, XCOM μ/ρ grids, G-P buildup coeffs)
│   │   ├── archer_diagnostic.json (NCRP 147 α,β,γ per material × kVp)
│   │   ├── archer_radionuclide.json (Oumano 2025, TG-108)
│   │   ├── tvl_megavoltage.json   (SRS 47/NCRP 151 TVL₁/TVLₑ primary+leakage)
│   │   ├── workloads.json         (NCRP 147 defaults per room type; SFDA NDRL DLPs)
│   │   ├── scatter.json           (scatter fractions; CT κ; BIR tertiary-scatter constants)
│   │   ├── radionuclides.json     (Γ, T½, RG 8.39 biokinetics)
│   │   ├── limits.json            (NCRP P; IAEA/NRRC constraints; occupancy factor menu)
│   │   └── references.json        (full bibliography; every dataset row carries a ref key)
│   ├── physics/               ← PART 2: calculation engine (pure functions, unit-tested)
│   │   ├── transmission.py        (Archer, TVL, μ+buildup models; multi-layer combiner)
│   │   ├── sources.py             (X-ray tube, CT, LINAC, radionuclide-patient source terms)
│   │   ├── barriers.py            (layered barrier object; transmitted kerma/dose at point)
│   │   ├── solver.py              (required-thickness solver; preferred-thickness rounding)
│   │   └── units.py
│   ├── regulatory/
│   │   └── limits.py              (framework selection; pass/fail verdict + margin)
│   └── report/
│       └── report.py              ← PART 4: audit-trail report (HTML→PDF) with references
├── ui/                        ← PART 3: Streamlit pages (one wizard per modality group)
└── tests/                     ← PART 4: validation vs published worked examples
```

- **Part 1 — Physics & regulatory data layer.** Extract all tables (scripts in `tools/`) from the local PDFs; encode literature data; every value carries `"ref"` + page/table annotation. Deliverable: datasets + spot-check script.
- **Part 2 — Calculation engine.** Transmission models; modality source terms; layered-barrier transmitted dose (primary & secondary separately); required-thickness solver. Deliverable: engine + unit tests.
- **Part 3 — User interface.** Streamlit wizard: modality → energy → workload (editable defaults) → geometry (distances, barrier height) → area & occupancy → framework/design goal → **material-mix builder** (add/remove layers) → results: transmitted doses, verdict, margin, required thickness per material, equivalent Pb/concrete, transmission plots. References tab. Deliverable: running app.
- **Part 4 — Integration, validation, reporting, docs.** Automated reproduction of published examples; report export; README/user guide; heavy code commenting pass; end-to-end assembly. Deliverable: validated v1.0.

Each part ends with a working, committed state and an update to this file.

---

## 5. Known limitations (to be stated inside the app and report)

1. Photons only — **no photoneutron design** for LINAC > 10 MV (mandatory warning shown; maze/door guidance text from SRS 47).
2. Multi-layer transmission = product of per-material broad-beam factors (standard, slightly conservative; spectral-hardening caveat documented; recommended layer ordering shown).
3. Skyshine, ducts and penetrations: qualitative guidance only in v1.0.
4. Saudi NRRC numeric design constraints pending the official NRRC-R-01 text (IAEA GSR Part 3 values used meanwhile, clearly labelled).

---

## 6. Open questions — ANSWERED by user 2026-06-10

1. UI language: **English only**.
2. **NRRC-R-01 provided** by user in `References\` → extract Saudi dose limits/constraints and cite exact clauses.
3. Default workloads: **agreed** — NCRP 147 survey values + SFDA NDRL DLPs, all editable.
4. Materials library: **as proposed is enough** (lead, ordinary concrete, barite concrete, steel, gypsum board, plate glass, lead glass, brick, wood + water/air for physics reference).
5. Report header: prepared by **Abdelaziz Habib** (institution/logo can be added later in `report.py`).
6. User may hit plan-usage limits: work is saved to disk continuously; this file is the resume point.

---

## 7. Log

| Date | Phase | Work done |
|------|-------|-----------|
| 2026-06-10 | 0 — Research | Identified all 6 user-provided references; located NCRP 147 key tables (pp. ≈82–101, 126–176); downloaded IAEA SRS 47 official PDF; confirmed Oumano 2025 radionuclide Archer fits, AAPM TG-108 method, NIST XCOM, ANSI/ANS-6.4.3 buildup, GSR Part 3 limits; Saudi NRRC site unreachable (action noted). User decisions captured (platform/scope/limits/method). Plan drafted and sent for approval. |
| 2026-06-10 | 1 — Data layer | Plan approved. Built `tools/` extraction scripts (identify, locate, extract, decode-mirrored, render, crop). Extracted Saudi NRRC-R-01 dose limits (doc pp.45–47) and NCRP 147 occupancy factors (Table 4.1). Solved NCRP 147 mirror-reversed/rotated tables via char-position decoder + high-zoom PNG rendering. Fully extracted **Table B.1 (primary)** and **Table C.1 (secondary)** Archer α/β/γ for 6 materials × 9 workload distributions + 6 single-kVp beams (30–150 kVp), cross-verified mantissas (decoder) vs exponents (rendered images). Wrote `references.json` (20 sources), `limits.json` (NCRP + IAEA/NRRC frameworks, occupancy factors). Encoding `archer_diagnostic.json` next. |
| 2026-06-10 | 1 — Data layer (cont.) | **COMPLETE & validated (8/8 JSON files parse).** `archer_diagnostic.json` (B.1 primary + C.1 secondary α/β/γ, 6 materials × 9 distributions + 6 single-kVp), `tvl_megavoltage.json` (SRS 47 Table 4 TVLs Co-60→24 MV, Table 5 scatter fractions, Table 11 scatter TVL, Table 8 patient transmission, photoneutron caveat), `radionuclides.json` (I-131/Tc-99m/F-18/Lu-177 TVL+Γ Oumano 2025; RG 8.39 I-131 biokinetics; TG-108 PET), `materials.json` (NIST μ/ρ Pb/concrete/Fe/water + densities), `scatter.json` (Table 4.7 secondary kerma; CT DLP Table 5.2; BIR ceiling scatter), `workloads.json` (Table 4.5 primary kerma; patient numbers; Saudi SFDA NDRLs; LINAC defaults). Validation anchors: SRS 47 Co-60 (TVL 218mm), RG 8.39 (60 mCi→4.59 mSv, 200 mCi→4.53 mSv). |
| 2026-06-10 | 2 — Engine | **COMPLETE & validated.** Built `radshield/` package: `data_loader.py` (cached JSON access + citation resolver), `physics/transmission.py` (Archer, TVL, mu+buildup models + analytic inverses + multi-layer combiner), `physics/beams.py` (maps modality/energy/material -> correct data+model), `physics/barriers.py` (layered Barrier, areal density, equivalent-thickness), `physics/sources.py` (diagnostic/CT/LINAC/radionuclide source terms + I-131 RG-8.39 biokinetics), `regulatory/limits.py` (NCRP & IAEA/NRRC design goals + pass/fail verdict), `physics/solver.py` (evaluate barrier, required & preferred thickness). Smoke test passes: SRS 47 Co-60 primary barrier = **1034 mm concrete (expected 1033)**; RG 8.39 = **4.53 mSv (exact)**; TVL/Archer sanity OK. |
| 2026-06-10 | 3 — UI | **COMPLETE.** `app.py` (Streamlit entry, 3 tabs), `ui/modality_config.py` (modality→engine mapping, 15 modalities in 5 groups), `ui/views.py` (calculator wizard: modality/energy/framework/occupancy → workload+geometry inputs → add/remove material-layer barrier builder → results: verdict, transmitted total & scattered/leakage, per-component table, required & preferred thickness per material, Pb/concrete equivalents, transmission plot; plus References & Limitations tabs; I-131 release panel). Verified with Streamlit AppTest: 0 render exceptions, all 5 modality groups OK. Fixed `use_container_width` deprecation. |
| 2026-06-11 | 4 — Validation & release | **COMPLETE.** `radshield/report/report.py` (self-contained HTML audit report → print to PDF; wired into UI download button). `tests/test_validation.py` (13 tests: transmission models, analytic-inverse round-trips, SRS 47 Co-60, RG 8.39 examples ×2, PET 511 keV TVL, multilayer product, verdict logic, report build, data-file load — all PASS). `README.md` (install, usage, method+references table, editing guide, structure, limitations). `requirements.txt`. Final integration verified. |

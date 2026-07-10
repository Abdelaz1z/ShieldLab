# ShieldLab Room Designer — Implementation Plan (for Opus to execute)
*Written by Fable 5, 2026-07-04, per the user's spec. This is the ShieldCAD MVP living inside ShieldLab
(this repo). The user draws/parametrizes a room, places the source, and the app either SUGGESTS the
shielding per wall (Design mode) or EVALUATES the user's declared shielding (Check mode), with a live
auto-updating top-view diagram and an exportable report (PDF default / Excel / HTML).*

**Executor notes (Opus):** work in THIS repo (`D:\Projects\Master\Master-26\Control Claude Program`).
Run with `py -3.11 -m streamlit run app.py`. Do NOT modify `radshield/physics/*` internals (validated
v1.0 — wrap, never edit). Complete Phase A fully (including the A6 gate) before touching Phase B.
Keep every new dependency pip-only (Streamlit Cloud constraint). After each phase: run the tests,
then ask the user to eyeball the UI.

---

## 0. Answers to the design questions (already decided — do not re-litigate)
- **Buildable NOW?** Yes. Phase A needs nothing beyond this repo. Phase B needs one prerequisite task
  (B1: persist the trained surrogate) which is included below. Nothing waits on the HPC.
- **Input style:** parametric builder (exact numbers, engineer-grade) + click-free live diagram that
  re-renders on every change ("auto-adjusts"). A freehand draw-canvas is Phase C (nice-to-have), NOT MVP
  — draw-canvases in Streamlit are fragile; engineers ultimately need exact mm anyway.
- **Two modes:** `Design` (app suggests thickness per wall/material) and `Check` (user declares
  material+thickness per wall → pass/fail + margin). Both always shown against the regulatory limit.
- **Engines:** `AnalyticalEngine` (wraps existing `radshield.physics` — NCRP-151/TG-108 broad-beam) is
  the default and the fallback. `SurrogateEngine` (thesis Extra-Trees + CQR + OOD guard) is Phase B,
  shown side-by-side; policy = *report both, design on the conservative one*.
- **Export:** user picks **PDF (default) / Excel / HTML** from a selector; `st.download_button`.

## 1. File layout to create
```
radshield/room/__init__.py
radshield/room/model.py        # dataclasses + JSON (de)serialization + validation
radshield/room/geometry.py     # distances, POP placement, per-wall solid geometry
radshield/room/engines.py      # EngineResult, AnalyticalEngine, (Phase B) SurrogateEngine
radshield/room/diagram.py      # matplotlib top-view renderer -> PNG bytes
radshield/room/report_room.py  # report dict -> PDF (fpdf2) / XLSX (openpyxl) / HTML (f-string)
pages/1_Room_Designer.py       # the Streamlit page (app.py becomes the multipage home)
tests/test_room_geometry.py
tests/test_room_engines.py
tests/golden_room.json         # the A6 golden case
models/                        # (Phase B) surrogate_bundle.joblib lands here
```

## 2. Data model (`model.py`) — the single source of truth (also ShieldCAD's future schema)
```python
@dataclass Room:      width_m, length_m, height_m=3.0
@dataclass Source:    isotope in {"Tc-99m","I-131","F-18"}; activity_MBq; patients_per_week;
                      residence_min; x_m; y_m   # position inside the room
@dataclass Opening:   kind in {"door","window","duct"}; center_along_wall_m; width_m;
                      lead_equiv_mm (door/window) | radius_mm (duct)
@dataclass AdjacentArea: name; occupancy_T (NCRP menu: 1, 1/2, 1/5, 1/8, 1/20, 1/40);
                      kind in {"controlled","public"}; design_goal_P_mSv_wk (default from
                      radshield.regulatory.limits by kind — keep overridable for KSA/NRRC values)
@dataclass Wall:      id in {"N","E","S","W"} (+ optional internal partitions later);
                      material1; thickness1_mm; material2=None; thickness2_mm=0;
                      adjacent: AdjacentArea; openings: list[Opening]
@dataclass RoomDesign: room; source; walls (exactly 4 in MVP); notes; schema_version="1.0"
```
- JSON round-trip (`to_json`/`from_json`) + `st.download_button` save / `st.file_uploader` load of the
  design itself (users iterate across sessions).
- Validation: source inside room; openings fit their wall; thicknesses ≥ 0; materials from the
  materials table (concrete, lead, steel, gypsum, lead_glass, barite_concrete — whatever
  `radshield.data_loader` already exposes; introspect it, don't hardcode blindly).

## 3. Geometry (`geometry.py`)
- Wall centerlines from room dims; perpendicular distance source→each wall.
- One auto **POP per wall**: 0.3 m beyond the wall's outer face, on the source-perpendicular
  (NCRP point of protection). `d_pop = perpendicular distance + thickness + 0.3`.
- One POP per opening (0.3 m beyond it, at the opening's center).
- Return a `BarrierPath` per (wall|opening): energy source→target geometry, distance d, and — for
  Phase B — the surrogate features (`thickness_mm`, `duct_radius_mm` if the path crosses a duct,
  `det_offset_mm` = lateral offset of the POP from the source-perpendicular through that wall, layer2).
- Unit tests: a 6×4 m room with source at center → hand-computed distances asserted to the mm.

## 4. Engines (`engines.py`)
```python
@dataclass EngineResult:
    barrier_id; B_required; B_achieved; dose_mSv_wk; passes: bool; margin;  # margin = B_req/B_ach
    suggested_thickness_mm: float|None      # Design mode
    ci_low, ci_high: float|None             # Phase B (CQR)
    ood: bool; engine: str                  # "analytical" | "surrogate" | "analytical (OOD fallback)"
```
**AnalyticalEngine (Phase A):**
- Weekly unshielded dose at POP from `radshield.physics.sources` (Γ, decay during residence — reuse
  whatever ShieldLab v1.0 already validated; do NOT re-derive constants).
- `B_required = P·T_occupancy-corrected / dose_unshielded(d_pop)` (exact formula per the existing
  ShieldLab solver conventions — introspect `physics/solver.py` and reuse its functions).
- `B_achieved` via `physics/transmission.py` (Archer/TVL + multi-layer combiner already there).
- Design mode: invert B(t) by bisection per selected material (or reuse solver if it already inverts).
- Openings: door/window = their own barrier (lead-equiv thickness); **duct = analytical cannot model →
  return `passes=None` + flag "needs surrogate/MC" in Phase A** (honest, and it advertises Phase B).
**SurrogateEngine (Phase B):** see §7.

## 5. UI (`pages/1_Room_Designer.py`)
Layout: `st.columns([1, 1.4])` — left = controls, right = live diagram + results.
- **Room & source:** number inputs (width/length), isotope selectbox, MBq, patients/week, residence
  minutes, source x/y sliders bounded by room dims.
- **Per-wall expanders (N/E/S/W):** adjacent-area name (text), occupancy T (selectbox with NCRP menu),
  area kind (controlled/public → default P auto-fills, editable), material1+thickness1 (thickness
  disabled in Design mode → shows the suggestion), optional layer2, "➕ add door / window / duct".
- **Mode toggle:** radio "Design (suggest) / Check (evaluate my design)".
- **Live diagram** (`diagram.py`): room rectangle, walls drawn as thick segments **colored by status**
  (green pass / red fail / grey needs-input / amber OOD-fallback), source = ★, POPs = ▲ with the
  computed distance annotated, openings drawn on their wall (door = gap + arc, window = double line,
  duct = ○), dims annotated. Re-render on every widget change — this is the "auto-adjusts" feel.
- **Results table** (`st.dataframe`): one row per barrier+opening: required vs achieved thickness (or
  B), dose mSv/wk vs limit, PASS/FAIL badge, margin ×, engine used.
- **Export block:** `st.selectbox("Format", ["PDF","Excel","HTML"])` + download button (§6).
- Session state: whole `RoomDesign` in `st.session_state`; save/load JSON buttons.

## 6. Report/export (`report_room.py`) — new deps: `fpdf2`, `openpyxl` (add to requirements.txt)
Common: build one `report = {inputs, per_barrier_results, diagram_png_bytes, engine_meta
(versions+dataset hash), timestamp, disclaimers}`.
- **PDF (default):** `fpdf2` (pure-python, deploys on Streamlit Cloud — do NOT use weasyprint, it needs
  system libs). Title block, inputs table, embedded diagram PNG, per-barrier results table with
  PASS/FAIL coloring, footnotes: "Decision-support output; requires qualified-expert (RSO) review. //
  Analytical tier: NCRP-151/TG-108 broad-beam (ShieldLab v1.0, validated). // Surrogate tier: MC-trained
  Extra Trees with conformal 95% CI and OOD guard (thesis, 2026)."
- **Excel:** openpyxl — sheets `Inputs`, `Barriers` (live formulas for margin = B_req/B_ach), `Meta`.
- **HTML:** simple styled f-string template (self-contained, inline CSS + base64 diagram).
- File name: `ShieldLab_RoomReport_YYYYMMDD_HHMM.{pdf|xlsx|html}`.

## 7. Phase B — surrogate integration
- **B1 (in thesis repo, prerequisite):** extend
  `D:\Projects\Master\Master-26\thesis_mc\src\train_surrogate_full.py` with `--save-bundle`:
  `joblib.dump({model, FEATURES, domain(TrainingDomain fitted), X_excised, cqr:{q_lo,q_hi,deltas},
  meta:{date, dataset:"nm_dataset_tierb_v2_final.csv", n=3182, test_r2, cqr95}}, "models/surrogate_bundle.joblib")`.
  Re-run the trainer once. Copy the bundle into THIS repo's `models/`.
- **B2:** `SurrogateEngine` loads the bundle lazily (app must run analytical-only if absent). Features
  per BarrierPath (energy = isotope principal line as trained; document this). Predict log10B → B, CI
  from CQR, OOD via box+density+`ExcisedRegion` proximity (import the logic — copy
  `surrogate_guard.py` into `radshield/room/` to keep this repo self-contained). OOD → analytical value
  + `engine="analytical (OOD fallback)"` + amber badge.
- **B3:** results table gains columns: `B surrogate (95% CI)` next to `B analytical`; design decisions
  use the conservative of the two; duct paths now get real numbers → show the leakage warning banner
  when duct B ≫ solid-wall B (the thesis headline, in the product).
- **B4:** pin `scikit-learn==1.9.0`, `joblib`, `numpy` in requirements.txt (bundle portability).

## 8. A6 / B5 acceptance gates (run before declaring done)
Phase A gate:
1. `tests/test_room_geometry.py` — hand-computed distances pass.
2. Golden room (`tests/golden_room.json`: Tc-99m 740 MBq, 40 pt/wk, 6×4 m, concrete walls, public
   corridor T=1/8 behind W): Design-mode suggested thickness reproduces the same answer computed
   directly with ShieldLab v1.0's existing solver on the same inputs (±1 mm).
3. Check mode: a deliberately thin wall shows FAIL + correct deficit; thickening it in the UI flips it
   green live.
4. JSON save→load→identical results. 5. All three exports download and open (PDF renders diagram).
Phase B gate:
1. Solid-wall path: |surrogate B − analytical B| within the paper's documented envelope on 5 spot cases.
2. A beam-shadow query (offset>230 mm territory) returns OOD-fallback (amber), never a raw prediction.
3. Duct case shows surrogate leakage ≫ analytical solid number with the warning banner.

## 9. Out of scope for this build (Phase C / ShieldCAD proper — do not start)
Freehand canvas, DXF/IFC import, floor/ceiling barriers, corner/maze surrogate, 3D U-Net dose-field
overlay (needs HPC W6), multi-room, Arabic UI toggle. The `RoomDesign` JSON schema above IS the
forward-compatible contract for all of it.

## 10. Housekeeping (do first, 2 min)
Move the stray GATE outputs out of this repo root (`edep_with_uncertainty_from_doseactor_*.mhd/.raw`
→ delete; they are run artifacts that belong to thesis_mc, already reproducible).

# ShieldLab — Design Brief

**For:** a product/UI designer redesigning ShieldLab
**From:** Abdelaziz Habib — Radiation Safety Officer (KSA), M.Sc. Radiation Protection
**Goal:** a modern, commercial, trustworthy interface for a radiation-shielding design tool

---

## 0. READ THIS FIRST — the constraint that decides everything

ShieldLab is currently a **Streamlit** (Python) app. Streamlit gives you very little design control:
a 5-colour theme, a fixed layout grammar (columns/expanders/tabs), and CSS injection as an escape
hatch. You cannot freely art-direct it.

**However — the entire engine is already decoupled from the UI.** The `shieldlab/` Python package
(physics, room model, cost optimiser, report generators) contains **zero Streamlit imports**. Only
three files touch Streamlit: `app.py`, `ui/views.py`, `pages/1_Room_Designer.py`.

So there are two honest tracks. **Please tell us which one your design targets, and design for it —
do not hand back a mockup that silently assumes Track B.**

| | **Track A — restyle in Streamlit** | **Track B — new front-end** |
|---|---|---|
| Scope | Theme + CSS + information architecture + custom HTML panels | React/Next front-end over a thin FastAPI wrapper on `shieldlab/` |
| Design freedom | Limited: Streamlit's widget shapes are fixed | Full |
| Effort | Days | Weeks |
| Risk | Low | Medium (new surface, but physics untouched) |
| Good for | Faster credibility lift, better hierarchy, cleaner density | A genuinely commercial product |

**What we want from you:** a design that works for **Track B** as the target vision, plus a
**Track A subset** — the highest-impact changes that are achievable inside Streamlit right now
(colour system, typography scale, spacing, the verdict card, the results table, iconography).

---

## 1. What ShieldLab is

A decision-support tool that calculates **radiation shielding** for medical facilities. You tell it
what radiation source a room contains (an X-ray tube, a CT scanner, a linear accelerator, or a
patient dosed with a radiopharmaceutical), the room geometry, and who is on the other side of each
wall. It returns how thick each barrier must be, whether the design meets the legal dose limits,
and what it will cost to build.

It is **not** a SaaS dashboard. It is a **safety instrument**. If it is wrong, people receive
radiation they should not have received, and a regulator rejects a hospital's licence. Every number
it displays is traceable to a published standard (NCRP 147/151, IAEA SRS 47, IAEA GSR Part 3, Saudi
NRRC, AAPM TG-108). That traceability is a feature and must be visible, not buried.

**What makes it commercially distinctive** (the things a competitor doesn't have — these deserve
design prominence):
1. **Two physics engines shown side by side** — a classical analytical calculation, and a
   Monte-Carlo-trained machine-learning model that reports a **95 % confidence interval** and
   flags when a geometry falls **outside its validated domain**. Honest uncertainty is the selling
   point. Most tools give you a single confident-looking number.
2. **A cost & material optimiser** — turns "how thick?" into "which material is cheapest, lightest,
   or thinnest, and what does the whole room cost?"
3. **A regulator-ready submission document** — a formal, signature-ready report, not a data dump.

---

## 2. Who uses it, and what they are deciding

| User | Context | The decision |
|---|---|---|
| **Radiation Safety Officer** (primary) | Hospital, under time pressure, legally accountable | "Is this room compliant? If not, what do I change?" |
| **Medical physicist** | Reviewing or signing off a design | "Do I trust this number? Where did it come from?" |
| **Hospital planner / architect** | Early design, budget-driven | "How thick, how heavy, how much does it cost?" |
| **Regulator** | Receives the output, not the app | "Is this submission complete and defensible?" |

They are technical but **not** software people. Many work in Arabic-speaking environments; the
interface is English (technical vocabulary is English in this field), but avoid idiom and clever
wordplay.

---

## 3. Current information architecture

**Two workspaces**, reached via Streamlit's page sidebar:

### A. Shielding Calculator — one barrier at a time
- **Sidebar:** modality group (Diagnostic X-ray / CT / Radiotherapy / Nuclear Medicine / I-131
  Therapy) → specific modality → regulatory framework (NCRP or IAEA-NRRC) → area type
  (controlled/uncontrolled) → occupancy factor T → design goal P (editable)
- **Left column:** modality-specific inputs (kVp, patients/week, distances, workload…)
- **Right column:** barrier builder — stack material layers (add/remove rows)
- **Results:** verdict card → 3 headline metrics → per-component breakdown table → **cost &
  material optimiser** → equivalents → transmission-vs-thickness chart → references → report downloads

### B. Room Designer — a whole room ("ShieldCAD")
- Mode toggle: **Design** (suggest thicknesses) vs **Check** (evaluate my design)
- Room dimensions, isotope, activity, patients/week, source position (X/Y sliders)
- **Four walls**, each expandable: adjacent area name, occupancy, area type, material layers, and
  **openings** — door / window / duct / maze, each with its own geometry
- **Live plan-view diagram** — a top-down room drawing, walls colour-coded by verdict
- Per-barrier results table (both engines side by side)
- **Room cost** roll-up
- Exports: PDF / Excel / HTML, 1-page clinical summary, **regulatory submission document**

---

## 4. Real content — design for THIS density, not lorem ipsum

Actual strings and numbers from the running app:

**Verdict card (calculator):**
> 🟢 **PASS** — ACCEPTABLE: transmitted 4.08e-24 mGy/week ≤ goal/T 0.1 mGy/week

**Verdict card (room):**
> 🟢 **PASS** — All evaluated barrier paths meet their regulatory design goals.
> Critical path: **Wall E** — 0.00939 mSv/week vs 0.02 mSv/week limit

**Per-barrier results table (8 columns, the densest thing in the app):**

| Barrier | Material | Suggested mm | Analytical B | Surrogate B (95 % CI) | Tier | Verdict | Margin × |
|---|---|---|---|---|---|---|---|
| Wall N | concrete | 280 | 4.24e-02 | 1.44e-02 [3.6e-03, 8.6e-02] | MC surrogate | PASS | 3.23 |
| Wall E | concrete | 170 | 1.47e-01 | 7.61e-02 [1.1e-02, 1.4e-01] | MC surrogate | PASS | 2.13 |

**Cost optimiser headline:**
> Cheapest: **250 mm Ordinary (Portland) concrete** (~$45/m², 588 kg/m²).
> Most compact: **14 mm Lead** (14 mm vs 250 mm — **30× the cost**).

**Room cost:**
> Shielding for the 4 solid walls as currently specified: **~$2,786** (36,378 kg of material).

**A warning that must never be missed:**
> ⚠️ **Wall N · duct:** the surrogate predicts duct-streaming transmission B≈3.2e-02 — about
> **18× the solid wall**. Duct penetrations dominate the dose here.

**Vocabulary:** transmission factor *B*, tenth-value layer (TVL), occupancy factor *T*, design goal
*P*, point of protection, areal density, controlled/uncontrolled area, primary vs secondary barrier.
Materials: concrete, lead, steel, barite concrete, brick, lead glass, gypsum.
Isotopes: Tc-99m, Lu-177, I-131, F-18, Ga-68.

Note the numbers are **scientific notation across many orders of magnitude** (1e-24 to 1e0). Any
design that assumes tidy 2-decimal currency figures will break.

---

## 5. Design principles for this domain

1. **Decision first, evidence underneath.** The RSO needs PASS/FAIL/MARGINAL in one glance, then
   *which* barrier is critical, then the numbers. Current order is right; the visual hierarchy is weak.
2. **Modern must not read as "startup".** Gradients, playful illustration, or marketing-style hero
   sections would *damage* credibility here. Target: precision instrument / clinical software /
   engineering tool. Think aviation or medical-device UI, not a fintech landing page.
3. **Uncertainty is a feature — show it honestly.** The 95 % CI and the out-of-domain flag must be
   legible without dominating. This is the hardest visual problem in the product (see §6).
4. **Traceability visible, not buried.** Every number can name its source standard. Design a
   lightweight way to surface that (hover, footnote marker, a "why?" affordance) without clutter.
5. **Never let a warning be pretty enough to ignore.** Duct-streaming and OOD warnings are safety-critical.
6. **Print is a real output.** The PDF/HTML reports are part of the product and get signed and filed.
7. **Density is required.** These users want the table. Do not hide data behind progressive disclosure
   for the sake of calm — hide *secondary* data, never the numbers they came for.

---

## 6. The hard problems (where design earns its keep)

1. **Two engines, one answer.** How do you show an analytical number and an ML number with a
   confidence interval side by side, make clear which drives the verdict, and not make the user feel
   the tool is unsure of itself? Today it is two extra table columns — functional, unresolved.
2. **Expressing a confidence interval** on a value spanning decades, inside a table row.
3. **Out-of-domain honesty.** When the ML model is outside its validated range, the app falls back to
   analytical and says so. That is a trust-building moment currently rendered as small amber text.
4. **The room editor.** Four walls × (materials + layers + openings) currently lives in nested
   expanders — functional, tedious. The plan-view diagram is generated server-side as a static image.
   An interactive plan view where you click a wall to edit it is the obvious win (Track B).
5. **Two workspaces, one product.** The Calculator and the Room Designer barely acknowledge each other.
6. **The empty state.** A first-time user sees a wall of inputs with no idea what "good" looks like.

---

## 7. Competitive context

Existing tools are either (a) spreadsheets and NCRP hand-calculations, (b) legacy desktop software with
1990s interfaces, or (c) a small number of modern web tools focused on one modality. None of them show
Monte-Carlo-grade uncertainty, none optimise cost, none generate a submission document. **The product
advantage is real; the interface currently undersells it.**

---

## 8. What we would like from you

1. **A visual direction** — colour system (including the PASS/MARGINAL/FAIL semantic set and how it
   works on dense tables), typography scale for numeric/scientific content, spacing, iconography.
2. **Key screens designed:** (a) Room Designer as the flagship, (b) Calculator results, (c) the
   regulatory submission document, (d) an empty/first-run state.
3. **The uncertainty pattern** — your solution to §6.1–6.3. This is the most valuable single thing.
4. **A Track A subset** — clearly marked: what of this is achievable by theme + CSS inside Streamlit
   without a rewrite, so we can ship a credibility lift immediately.
5. Light/dark is optional. Accessibility is not: these are clinical users, colour must never be the
   only carrier of PASS/FAIL.

**Not needed:** a marketing site, a logo (unless you want to), or onboarding flows.

---

## 9. How to run it yourself

```
py -3.11 -m streamlit run app.py     # http://localhost:8501
```
Live demo: https://shieldlab.streamlit.app — the Room Designer is the second page in the sidebar.

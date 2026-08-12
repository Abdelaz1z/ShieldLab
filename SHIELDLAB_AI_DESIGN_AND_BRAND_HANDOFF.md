# ShieldLab — Product, UX, Design System, and Logo Handoff

**Purpose:** Give this file to Claude Design, Manus AI, Figma Make, or another product-design AI as the complete source of truth for redesigning ShieldLab and creating its logo.

**Product name:** ShieldLab  
**Category:** Medical radiation shielding decision-support software  
**Primary markets:** Hospitals, imaging centers, radiotherapy facilities, nuclear-medicine departments, engineering consultants, and radiation-safety teams  
**Primary languages:** English and Arabic, with complete LTR and RTL support  
**Current application:** Python 3.11 and Streamlit 1.58  
**Future design target:** A commercial web-product experience that can first be adapted to Streamlit and later implemented in a custom React/Next.js frontend without changing the calculation engine

---

## 1. Master Assignment for the Design AI

Act as a senior product designer and brand designer specializing in clinical, engineering, and safety-critical software.

Create a complete visual identity and product experience for **ShieldLab**, a professional radiation-shielding assessment platform. The product must feel precise, trustworthy, modern, technically advanced, and commercially credible. It must not feel like a generic admin dashboard, an academic prototype, a playful startup, or a consumer wellness application.

Your work must include:

1. Three distinct visual directions before selecting a final direction.
2. An original ShieldLab logo system and wordmark.
3. A complete design system for English LTR and Arabic RTL.
4. High-fidelity desktop and mobile designs for the key screens defined in this file.
5. Interaction states, safety-status patterns, complex tables, charts, forms, reports, empty states, warnings, and validation states.
6. A clickable prototype or implementation-ready frontend specification.
7. A clear separation between what can be implemented inside Streamlit now and what requires a future custom frontend.

Do not change, reinterpret, or simplify the physics, regulatory logic, units, safety states, or calculation outputs. Do not invent authentication, billing, collaboration, AI chat, or other product features that are not described here. Propose optional future ideas separately from the core design.

---

## 2. What ShieldLab Is

ShieldLab is a decision-support application for designing and checking **photon radiation shielding in medical facilities**.

The user describes a radiation source, workload, geometry, occupied areas, regulatory framework, and shielding construction. ShieldLab calculates how much radiation passes through each barrier, compares the result with the applicable design goal, identifies unsafe or uncertain paths, recommends shielding thicknesses, compares materials and cost, and produces evidence for technical review and regulatory submission.

ShieldLab supports two levels of work:

- **Barrier Assessment:** Analyze one barrier or shielding assembly in detail.
- **Room Designer:** Analyze a complete rectangular room with four walls, adjacent areas, openings, source position, shielding materials, and a live plan view.

ShieldLab is not a dose-tracking application, electronic medical record, treatment-planning system, or radiation-monitoring dashboard. It is an engineering and radiation-protection design instrument.

---

## 3. The Problem It Solves

Radiation-shielding design is commonly performed with spreadsheets, hand calculations, reference tables, and legacy desktop tools. That creates several problems:

- Important inputs are spread across different worksheets and standards.
- A simple PASS result can hide a narrow safety margin or uncertain model behavior.
- Openings such as ducts, doors, windows, and maze entrances may dominate the radiation path.
- Material thickness, structural load, construction cost, and regulatory evidence are often handled separately.
- Reviewers need traceable methods and references, not only a final number.
- Arabic-speaking users often work with an English-only technical workflow.

ShieldLab combines these tasks in one structured product while making uncertainty and limitations visible.

---

## 4. What Makes ShieldLab Different

The design must visibly communicate these product advantages:

### 4.1 Decision-first workflow

The user sees the overall outcome first, followed by the critical barrier or path, safety margin, evidence, and next action.

### 4.2 Analytical and surrogate engines

The Room Designer can compare:

- A classical analytical shielding calculation.
- A geometry-aware surrogate trained from Monte Carlo campaign data.

The surrogate may provide a 95% confidence interval. When a query is outside the validated surrogate domain, ShieldLab visibly falls back to the analytical tier or states that detailed Monte Carlo evaluation is required.

### 4.3 Honest uncertainty

ShieldLab does not hide uncertainty behind a confident green result. A path can require review when:

- Its safety margin is below the review threshold.
- A surrogate 95% upper bound crosses the regulatory goal.
- The path is outside the surrogate’s validated domain.
- A duct, maze, deep-wall, or other model limitation requires independent review.
- A path cannot be evaluated reliably.

### 4.4 Material and cost decisions

ShieldLab helps users compare practical shielding options by required thickness, installed cost, areal mass, and footprint. The room workflow also rolls up solid-wall shielding cost.

### 4.5 Technical and regulatory evidence

The product produces reports that preserve the result, inputs, units, status, review reasons, per-path evidence, and technical limitations.

### 4.6 Bilingual operation

The application supports English and formal professional Arabic. Language switching must be presentation-only: values, calculations, project state, and decisions must not reset or change.

---

## 5. Primary Users

### 5.1 Radiation Safety Officer — primary user

**Context:** Responsible for radiation protection in a hospital or medical facility. Often works under time pressure and may be legally accountable for the shielding recommendation.

**Main questions:**

- Does this barrier or room meet the selected design goal?
- Which path is critical?
- Is the margin comfortable or does it require review?
- What needs to change if the design fails?
- Can I defend this result to management or a regulator?

### 5.2 Medical physicist

**Context:** Reviews methods, assumptions, uncertainty, and calculations before sign-off.

**Main questions:**

- Which engine produced this result?
- What is the confidence interval?
- Is the query inside the validated domain?
- What reference and method support this number?
- Are units and occupancy assumptions correct?

### 5.3 Hospital planner, architect, or shielding consultant

**Context:** Needs practical dimensions, cost, wall load, and construction implications.

**Main questions:**

- How thick must the barrier be?
- Which material is most economical, lightest, or most compact?
- How do doors, windows, ducts, and wall dimensions affect the design?
- What is the approximate room shielding cost?

### 5.4 Regulator or independent reviewer

**Context:** Usually consumes an exported report rather than using the application directly.

**Main questions:**

- Is the calculation basis stated?
- Are assumptions and limitations disclosed?
- Are every path and unit shown consistently?
- Is the result suitable for approval, or does it explicitly require review?

---

## 6. Safety and Trust Model

The design must treat status as a structured safety language, not decorative color.

| Status | Meaning | Required presentation |
|---|---|---|
| **PASS** | Evaluated paths meet the design goals with no review trigger | Green may support the state, but always include the word PASS, an icon, the critical result, and the safety margin |
| **REVIEW REQUIRED** | Point estimates may pass, but uncertainty, narrow margin, out-of-domain behavior, or another assurance issue prevents an unqualified pass | Amber, explicit “Review Required” wording, reason list, affected paths, and a recommended next action |
| **FAIL** | At least one evaluated path exceeds its regulatory design goal | Red, explicit FAIL wording, failed paths, dose-versus-goal comparison, and corrective action |
| **NOT EVALUATED / NEEDS MC** | The available model cannot produce a defensible result | Neutral or amber technical state, never green; explain what is missing and what analysis is required |

Rules:

- Never use color as the only status signal.
- Never display a green room plan while a path requires review.
- Safety warnings must appear before detailed results and exports.
- Confidence intervals and fallback behavior must be understandable without opening a hidden panel.
- PASS, REVIEW REQUIRED, FAIL, and NOT EVALUATED must remain visually distinct in normal vision, color-vision deficiency, grayscale printing, and high-contrast modes.

---

## 7. Supported Clinical and Engineering Scenarios

### 7.1 Diagnostic X-ray

- General radiography room.
- Chest bucky wall.
- Floor or table barriers.
- Dedicated chest room.
- Fluoroscopy and R&F.
- R&F radiographic tube.
- Mammography.
- Cardiac angiography and cath lab.
- Peripheral or neuro angiography.
- Dental panoramic and cephalometric rooms.

Typical inputs include kVp, patients per week, primary distance, secondary distance, and modality-specific workload assumptions.

### 7.2 Computed tomography

- CT scanner scatter assessment.
- Head, chest, abdomen, pelvis, and body-average exam mixes.

Typical inputs include DLP, examinations per week, exam distribution, and distance to the occupied point.

### 7.3 Radiotherapy

- LINAC and Co-60 megavoltage vault barriers.
- Primary and secondary barrier modes.
- Co-60 and 4–24 MV photon energies.

Typical inputs include workload, use factor, IMRT factor, and primary or secondary distances.

### 7.4 Nuclear medicine

- Tc-99m gamma camera or SPECT room.
- F-18 PET or PET-CT room.
- Lu-177 therapy room.

Typical inputs include activity, distance, and occupied hours.

### 7.5 Iodine-131 therapy

- I-131 therapy room or isolation ward.
- Released-patient evaluation is also supported in the barrier workflow.

Typical inputs include activity, distance, occupied hours, and clinical condition where applicable.

---

## 8. Regulatory and Unit Context

Supported regulatory bases include:

- **NCRP weekly design goals.**
- **IAEA GSR Part 3 / Saudi NRRC constraints.**

Adjacent areas are classified as controlled or uncontrolled/public and use an occupancy factor **T**. Users may apply a framework default or enter a custom design goal **P**.

The interface must preserve the distinction between:

- Calculated photon dose, commonly displayed in `mSv/week`.
- NCRP design goals, displayed in `mGy/week` with the disclosed photon approximation `1 mGy ≈ 1 mSv` where relevant.
- IAEA/NRRC goals, displayed in `mSv/week`.

Never silently relabel a value to make the table look simpler. Units must be attached to values and must remain LTR inside Arabic interfaces.

---

## 9. Workspace A — Barrier Assessment

This workspace evaluates a single barrier assembly.

### 9.1 Setup inputs

- Facility or modality group.
- Specific modality.
- Regulatory framework.
- Controlled or uncontrolled/public area classification.
- Suggested occupancy area and occupancy factor T.
- Optional custom design goal P.

### 9.2 Source and workload inputs

Inputs change by modality. They may include:

- Maximum energy in kVp or MV.
- Radionuclide.
- Patients or examinations per week.
- DLP.
- Photon workload in Gy/week.
- Activity.
- Occupied hours.
- Use factor.
- IMRT factor.
- Primary and secondary distances.
- Secondary geometry or scatter angle.

### 9.3 Barrier builder

The user creates a multilayer barrier. Each layer has:

- Stable identity.
- Material.
- Thickness in millimeters.
- Add, remove, and reset controls.
- Calculated areal load.

Representative materials include ordinary concrete, barite concrete, lead, steel, gypsum, brick, plate glass, lead glass, wood, and water/reference materials where supported.

### 9.4 Results

The decision order is:

1. Overall PASS, REVIEW REQUIRED, or FAIL.
2. Plain-language decision headline.
3. Calculated transmitted dose versus applied goal.
4. Safety margin.
5. Primary, scatter, and leakage/component evidence where applicable.
6. Required build and current build.
7. Material alternatives and optimization.
8. Transmission-versus-thickness visualization.
9. Method and source references.
10. Export actions.

### 9.5 Barrier exports

- Clinical one-page PDF summary.
- Detailed HTML audit report.

Arabic project names are safe in HTML. The current validated PDF workflow requires English identifiers; the interface explains this rather than altering the user’s text.

---

## 10. Workspace B — Room Designer

This is the flagship workspace. It evaluates a complete rectangular room.

### 10.1 Project and command bar

- Design mode: suggest required shielding thicknesses.
- Check mode: evaluate the user’s declared construction.
- Regulatory framework selector.
- Load room project from JSON.
- Download room project as JSON.
- Preserve language and project state across loading and navigation.

### 10.2 Room geometry

- Width.
- Length.
- Height.
- Source X position.
- Source Y position.

### 10.3 Source definition

- Isotope.
- Activity per patient.
- Patients per week.
- Residence time.

Room-design defaults currently use an F-18 source, but the design must support other available radionuclides without assuming that the label length or energy is fixed.

### 10.4 Wall editor

Each of the North, East, South, and West walls contains:

- Adjacent area name.
- Occupancy preset or custom factor T.
- Controlled or public classification.
- Optional custom design goal.
- Primary shielding material and thickness.
- Optional second material and thickness.
- Openings.

The recommended future interaction is to select a wall directly from the plan and edit it in a contextual side panel. A Streamlit-compatible version may retain the wall selector and cards but must reduce nested, repetitive expanders.

### 10.5 Openings

Supported opening types are:

- Door.
- Viewing window.
- Duct.
- Maze entrance.

Opening properties may include position along the wall, width, lead equivalence, duct radius, return-wall material and thickness, corridor length, and shadow offset.

Openings are safety-critical paths. They must be visible on the plan and separately listed in results. Do not visually merge an opening result into the solid-wall result.

### 10.6 Live plan view

The room plan must show:

- Room outline and dimensions.
- North, East, South, and West labels.
- Source position.
- Adjacent areas.
- Doors, windows, ducts, and maze paths.
- Path status.
- Selected wall.
- Critical path.

The future target should support selecting a wall or opening from the plan. The current Streamlit implementation renders a static PNG plan, so direct manipulation belongs to the custom-frontend track.

### 10.7 Room result hierarchy

1. Overall decision.
2. Review reasons and safety notices.
3. Critical path.
4. Headline metrics.
5. Color-independent room plan status.
6. Per-wall and per-opening result table.
7. Analytical and surrogate evidence.
8. Confidence intervals, domain state, and engine notes.
9. Failure explanations and recommended action.
10. Cost and material comparison.
11. Export package.

### 10.8 Room exports

- Detailed PDF.
- Detailed HTML.
- Excel workbook.
- One-page decision summary PDF.
- Regulatory submission HTML document.
- Room-design JSON.

The exported status, path verdicts, units, warnings, and review reasons must match the on-screen decision exactly.

---

## 11. Methods and Safety Surfaces

The product includes dedicated areas for:

- Calculation method overview.
- Reference library and source citations.
- Model scope.
- Assumptions.
- Workspace capability boundaries.
- Regulatory-validation notice.
- Qualified-expert sign-off warning.

These areas are not marketing pages. They are part of the evidence chain and should be readable, navigable, and easy to cite.

---

## 12. Important Limitations the Design Must Surface

- ShieldLab is decision-support software; final construction designs require review and sign-off by a qualified Radiation Safety Officer or medical physicist.
- The application models photons. LINAC photoneutron design above 10 MV is outside the supported scope.
- Scanner- and facility-specific survey or isodose data may be required for final design.
- Multi-layer broad-beam approximations and model-domain limits must remain visible.
- Deep-tail surrogate intervals may be withdrawn when prospective validation does not support a reliable interval; deep-wall geometry bias is disclosed separately.
- Some out-of-domain paths require a full Monte Carlo evaluation.
- Duct and maze results may be screening-tier results and must not be visually presented as definitive approval.
- Cost output is an engineering estimate. Doors, windows, ducts, and mazes are not included in the current solid-wall cost roll-up.

Design warnings by severity and required action. Do not place every limitation in the same generic yellow box.

---

## 13. Core User Journeys

### Journey A — Check an existing barrier

1. Select modality and regulatory basis.
2. Confirm occupancy and design goal.
3. Enter workload and distances.
4. Declare barrier layers.
5. See the decision immediately.
6. Inspect dose, goal, margin, component evidence, and references.
7. Compare corrective material options if necessary.
8. Export an auditable summary.

### Journey B — Design a new nuclear-medicine room

1. Create or load a room project.
2. Choose Design mode and regulatory framework.
3. Enter room geometry and source workload.
4. Position the source.
5. Define each adjacent area and occupancy.
6. Add doors, windows, ducts, or a maze.
7. Review the live plan and suggested wall builds.
8. Resolve every FAIL or REVIEW REQUIRED path.
9. Compare cost and structural load.
10. Export the room file and regulatory evidence.

### Journey C — Review a submitted design

1. Load the JSON project.
2. Switch to Check mode.
3. Confirm that inputs and units match the design documents.
4. Review overall decision and all review triggers.
5. Compare analytical and surrogate evidence.
6. Inspect out-of-domain and confidence-interval notes.
7. Download the formal review package.

---

## 14. Information Architecture Target

### Global product shell

- ShieldLab logo and product name.
- Language switcher: English / العربية.
- Workspace navigation.
- Current project identity and saved-state indicator.
- Contextual help or methods access.

### Recommended primary navigation

1. **Home / Start** — concise workspace chooser, recent-project concept only if persistence is later implemented, sample projects, and product scope.
2. **Barrier Assessment** — single-barrier workflow.
3. **Room Designer** — complete-room workflow.
4. **Methods & References** — technical basis.
5. **Safety & Scope** — limitations and sign-off requirements.

Do not invent a dashboard full of meaningless utilization charts. The home screen should help the user begin a real shielding task.

---

## 15. Required Key Screens

Create high-fidelity designs for at least:

1. Home / workspace chooser.
2. Barrier Assessment setup with real form density.
3. Barrier Assessment PASS result.
4. Barrier Assessment REVIEW REQUIRED or FAIL result.
5. Room Designer in Design mode.
6. Room Designer in Check mode.
7. Room Designer with a selected wall and selected opening.
8. Room result with a duct-streaming warning.
9. Room result with an out-of-domain or Monte Carlo-required path.
10. Cost and material comparison.
11. Methods and references.
12. Regulatory report preview.
13. First-run empty state.
14. Validation-error state.
15. Mobile views for the Barrier Assessment and Room Designer review flow.
16. Arabic RTL versions of the main Barrier Assessment and Room Designer screens.

Use real technical content, scientific notation, long Arabic labels, mixed Arabic/English units, and multi-line warnings. Do not use lorem ipsum.

---

## 16. Design Personality

ShieldLab should feel:

- Precise.
- Calm under pressure.
- Technically advanced.
- Clinically trustworthy.
- Transparent about uncertainty.
- Commercial and mature.
- Efficient for repeated professional use.
- Distinctive without becoming theatrical.

ShieldLab should not feel:

- Like a generic Bootstrap admin template.
- Like a cryptocurrency, fintech, cybersecurity, or AI-chat product.
- Like a university project or scientific notebook.
- Like a hospital patient portal.
- Playful, neon, game-like, or excessively animated.
- Empty and minimal at the expense of technical evidence.
- Dark-on-dark, pale-on-pale, or dependent on low-contrast placeholder text.

Use visual interest through composition, hierarchy, purposeful geometry, data visualization, and a recognizable brand motif—not through decorative gradients covering every surface.

---

## 17. Design System Requirements

### 17.1 Color system

Propose the palette; do not inherit the current application colors automatically.

The system must define tokens for:

- Canvas.
- Primary surface.
- Raised surface.
- Muted surface.
- Primary text.
- Secondary text.
- Disabled text and controls.
- Border and strong border.
- Brand primary and brand secondary.
- Interactive hover, active, selected, and focus states.
- PASS, REVIEW REQUIRED, FAIL, NOT EVALUATED, and informational states.
- Data-series colors suitable for color-vision deficiency.
- Print and grayscale equivalents.

Accessibility requirements:

- WCAG 2.2 AA minimum for normal text and controls.
- Prefer 7:1 for critical body text when practical.
- At least 3:1 for meaningful component boundaries and graphical objects.
- Disabled controls must remain readable; lower emphasis must not mean invisible.
- Test every sidebar, table, input, chart, tab, status card, and export-preview state.

### 17.2 Typography

Requirements:

- A professional Latin typeface and a compatible Arabic typeface with similar visual weight.
- Body and input text approximately 16 px or larger on desktop.
- Labels approximately 14 px or larger.
- Captions approximately 13 px or larger.
- Large, clear page titles without excessive marketing scale.
- Tabular numerals for measurements and comparisons.
- Scientific notation must be legible and aligned.
- Units must not wrap away from values.
- Arabic diacritics, mixed Latin acronyms, isotope names, and units must remain readable.

### 17.3 Spacing and layout

Define a consistent spacing scale and responsive grid.

The product needs:

- Dense but breathable forms.
- Strong grouping of related inputs.
- Clear separation between setup, decision, evidence, and export.
- Sticky context or decision areas only when they do not hide content.
- Desktop layouts optimized for approximately 1280–1600 px widths.
- Functional tablet and 390 px mobile layouts.
- No horizontal overflow except intentional data-table scrolling.

### 17.4 Elevation, borders, and shape

- Use a small, consistent radius family.
- Use elevation sparingly to express hierarchy, not decoration.
- Inputs and cards require visible boundaries on both light and dark surfaces.
- Safety states need stronger structure than ordinary informational cards.
- Avoid excessive glassmorphism and translucent text surfaces.

### 17.5 Motion

- Motion must communicate state, selection, or spatial relationship.
- Use transform and opacity only where possible.
- Keep interactions fast and interruptible.
- Respect `prefers-reduced-motion`.
- Never animate a safety result in a way that delays or obscures it.

### 17.6 Iconography

- Use a consistent professional outline or restrained duotone family.
- Create clear icons for source, barrier, room, wall, door, window, duct, maze, cost, report, reference, warning, confidence interval, and Monte Carlo review.
- Icons supplement labels; they do not replace critical words.

---

## 18. Required Component Library

Design every component with default, hover, focus-visible, active, selected, disabled, loading, error, and RTL states where relevant.

- Product header and sidebar.
- Language switcher.
- Workspace switcher.
- Project command bar.
- Step or workflow navigation.
- Text, numeric, select, radio, checkbox, segmented, and slider controls.
- Unit-aware numeric field.
- Material-layer row and layer stack.
- Occupancy selector.
- Wall selector.
- Opening editor.
- Context summary strip.
- Metric card.
- Overall decision card.
- Review-reason list.
- Inline validation message.
- Safety warning and limitation notice.
- Engine badge.
- In-domain / out-of-domain badge.
- Confidence-interval display.
- Scientific-value cell.
- Results table with sticky headers and critical-row emphasis.
- Material comparison card or table.
- Cost summary.
- Room plan legend and interactive wall/opening states.
- Tabs and accordions.
- Reference citation and method drawer.
- Empty state and sample-project card.
- Export format selector and download action.
- Report preview.
- Toast or saved-state notification if a future frontend supports it.

---

## 19. Complex Data Presentation Requirements

### 19.1 Scientific notation

Values may span from approximately `1e-24` to `1e0`. Support:

- Aligned mantissa and exponent.
- Full precision on demand.
- A human-readable interpretation where useful.
- Copyable values.
- Stable width so tables do not jump.

### 19.2 Dose versus goal

Always make the relationship explicit:

- Calculated dose.
- Applied goal or `P/T`.
- Unit for each.
- Safety margin multiplier.
- Which value drives the decision.

### 19.3 Two-engine comparison

Design a pattern that shows:

- Analytical result.
- Surrogate point estimate.
- 95% confidence interval when valid.
- The engine used for the displayed decision.
- In-domain, fallback, interval-withdrawn, or needs-MC state.
- A short explanation without forcing users to decode model terminology.

### 19.4 Tables

Tables may contain barrier/path, declared build, suggested build, analytical transmission, surrogate transmission, confidence interval, dose, limit, margin, engine tier, and status.

Requirements:

- Critical columns remain visible.
- Mobile uses a purposeful card or row-detail adaptation, not a crushed desktop table.
- Users can visually scan failed and review-required paths.
- Sticky column behavior must work in both LTR and RTL.
- Status, units, and path identity must never disappear during horizontal scrolling.

---

## 20. English and Arabic Requirements

- English uses LTR; Arabic uses RTL.
- The brand name **ShieldLab** remains in English and uses `translate="no"` behavior in implementation.
- All navigation, headings, controls, decisions, warnings, and primary help content require professional Arabic.
- Canonical engine keys, material IDs, JSON schema keys, and calculation values are never translated internally.
- Units, numbers, scientific notation, isotope symbols, NCRP, IAEA, NRRC, kVp, MV, MBq, mGy/week, and mSv/week remain directionally isolated LTR.
- Layout must use logical start/end spacing rather than hardcoded left/right assumptions.
- Arabic is not a mirrored afterthought. Design the Arabic screens deliberately and test long labels.
- Language switching must preserve current inputs, material layers, room project, active decision, and status.

---

## 21. Accessibility Requirements

- Target WCAG 2.2 AA.
- Provide a visible keyboard focus state for every interactive element.
- Maintain semantic heading order.
- Provide labels for every form control.
- Make touch targets approximately 44–48 px minimum.
- Do not disable browser zoom.
- Do not use color alone for meaning.
- Provide text alternatives for diagrams and room plans.
- Support keyboard navigation through wall and opening selection.
- Announce recalculated decisions and validation errors appropriately without overwhelming screen-reader users.
- Respect reduced-motion preferences.
- Test 200% zoom, 390 px mobile width, RTL, long project names, and long validation messages.

---

## 22. Logo and Brand Identity Brief

### 22.1 Brand name

**ShieldLab** — capital S and L. Do not rename it or translate the wordmark.

### 22.2 Brand idea

ShieldLab combines:

- Protection and shielding.
- Scientific calculation.
- Clinical responsibility.
- Engineering precision.
- Transparent evidence.

The identity should communicate “measured protection” rather than “danger.”

### 22.3 Suggested concept territories

Develop at least three distinct logo concepts from territories such as:

1. **Shield + measured attenuation:** A shield or barrier with a beam entering and a reduced beam leaving.
2. **Shield + structured layers:** A geometric shield built from layered barrier segments.
3. **SL monogram + protection geometry:** An original S/L construction that implies a barrier, room corner, or point of protection.
4. **Room plan + protective field:** A simplified plan-view enclosure with a protected point outside the wall.
5. **Scientific mark:** A restrained mark based on transmission, orbit, or field lines without looking like an AI company.

The radiation trefoil may appear only as a subtle secondary reference if it improves recognition. Do not make the product look like an emergency hazard sign.

### 22.4 Logo requirements

- Original and ownable silhouette.
- Simple enough to remain recognizable at 16–24 px.
- Works as app icon, favicon, report mark, sidebar logo, and monochrome stamp.
- Works on light and dark backgrounds.
- Strong in one color before gradients or effects are added.
- Compatible with English and Arabic layouts.
- Wordmark must remain legible in clinical reports.
- Avoid tiny details, thin radiation rays, or effects that fail in print.

### 22.5 Avoid

- Generic shield with a checkmark as the only idea.
- Generic medical cross.
- Skull, danger tape, glowing nuclear symbol, or aggressive hazard language.
- Chat bubbles, robot heads, sparkles, or “AI” stars.
- Cybersecurity padlock aesthetics.
- Gaming, crypto, or neon-tech styling.
- Stock-logo appearance.
- Letterforms that confuse ShieldLab with a laboratory-testing company.

### 22.6 Logo deliverables

- Primary horizontal logo.
- Stacked logo.
- Symbol-only mark.
- Wordmark-only version.
- Light, dark, monochrome, and grayscale variants.
- App icon and favicon sizes.
- Clear-space and minimum-size rules.
- Color specifications in HEX, RGB, CMYK, and accessible digital token roles.
- SVG source with outlined and live-text variants where appropriate.
- PNG exports at common sizes.
- Short rationale for each concept and the final selection.

---

## 23. Voice and Interface Copy

The voice is:

- Direct.
- Calm.
- Specific.
- Professional.
- Honest about uncertainty.
- Focused on the user’s next action.

Good examples:

- “Review Required — the 95% upper bound crosses the applied design goal.”
- “Wall E is the critical path.”
- “Increase the declared shielding or request detailed Monte Carlo review.”
- “Outside the surrogate’s validated domain; the analytical fallback is shown.”

Avoid:

- “Awesome! Your room is safe.”
- “The AI thinks this should be fine.”
- “Something went wrong.”
- Vague CTA labels such as “Continue” when a specific action is available.
- Marketing superlatives inside the engineering workflow.

---

## 24. Technical Boundaries

### Current implementation track — Streamlit

Streamlit controls the basic widget and layout behavior. A practical near-term design can change:

- Theme and CSS tokens.
- Page hierarchy.
- Typography and spacing.
- Custom HTML status, metric, context, and table components.
- Sidebar presentation.
- Tabs, cards, warnings, and report styling.
- Static room-plan presentation.

It cannot provide a fully freeform canvas or a deeply interactive plan editor without custom components.

### Future implementation track — custom frontend

A React/Next.js frontend over a thin Python API can support:

- Direct wall and opening selection from an interactive plan.
- Rich responsive tables.
- Persistent project navigation.
- Better undo, autosave, and command patterns.
- First-class design-system components.
- Smooth bilingual routing and accessible interaction.

The calculation engine in `shieldlab/` is already separated from the Streamlit presentation layer. The redesign must preserve the engine as the source of truth.

### Do not modify without explicit approval

- Physics formulas.
- Regulatory thresholds.
- Unit conversions.
- PASS / REVIEW REQUIRED / FAIL logic.
- Surrogate-domain safeguards.
- Report evidence semantics.
- JSON project schema.

---

## 25. Required Design Deliverables

### Phase 1 — Direction

- Three clearly different mood boards or visual directions.
- Proposed color systems with measured contrast.
- Typography pairing for English and Arabic.
- Three logo concepts.
- One representative Barrier Assessment screen per direction.
- Explanation of why each direction fits a safety-critical commercial product.

Stop for owner selection before developing the full system.

### Phase 2 — Identity and system

- Final logo package.
- Design tokens.
- Component library.
- Status and uncertainty patterns.
- Icon style.
- Chart and table rules.
- Responsive and RTL behavior.
- Print/report rules.

### Phase 3 — Product screens

- All key screens listed in Section 15.
- Desktop, mobile, English, and Arabic variants.
- Clickable prototype for both main journeys.
- Validation, warning, loading, empty, and disabled states.

### Phase 4 — Implementation handoff

- Figma variables or equivalent token export.
- Component specifications.
- Spacing, typography, and color values.
- Interaction notes.
- Asset exports.
- Clear list of Streamlit-compatible changes.
- Clear list of custom-frontend-only changes.

---

## 26. Acceptance Criteria

The work is complete only when:

- A first-time user can identify the two workspaces and begin the correct task without explanation.
- An experienced RSO can identify overall status, critical path, dose, goal, margin, engine, and required action within seconds.
- REVIEW REQUIRED cannot be mistaken for PASS.
- Duct, maze, out-of-domain, deep-wall, and confidence-interval warnings are visible before approval or export.
- English and Arabic interfaces preserve the same hierarchy and functionality.
- Numeric and unit content remains readable at realistic density.
- Every form control and disabled state passes contrast and focus review.
- The design works at desktop and 390 px mobile widths.
- The room plan remains understandable without relying only on color.
- The logo works as a 24 px app mark and as a monochrome report mark.
- The design is recognizably ShieldLab rather than a generic dashboard template.
- No physics, status, unit, or regulatory behavior is changed.

---

## 27. Copy-Ready Prompt to Send with This File

```text
You are designing ShieldLab, a commercial, bilingual radiation-shielding decision-support product for Radiation Safety Officers, medical physicists, hospital planners, and technical reviewers.

Treat the attached “ShieldLab — Product, UX, Design System, and Logo Handoff” file as the authoritative product specification. Read it completely before producing anything.

Your task is to create the brand identity, logo system, design system, and product UX described in the file. Begin with Phase 1 only: three genuinely different visual directions, three original logo concepts, an English/Arabic typography pairing, an accessible semantic-color proposal, and one representative Barrier Assessment screen for each direction. Use realistic technical content from the specification, not lorem ipsum.

The product must feel precise, calm, technically advanced, clinically trustworthy, commercially mature, and honest about uncertainty. It must not look like a generic admin dashboard, a cybersecurity product, an AI-chat application, a playful startup, or a university prototype.

Preserve all calculations, safety states, units, regulatory meaning, review triggers, engine distinctions, and project data. Do not invent authentication, billing, collaboration, AI chat, or unrelated features. Clearly label any optional future idea as optional.

Design for both English LTR and Arabic RTL. Maintain WCAG 2.2 AA contrast, visible focus, color-independent safety states, legible disabled controls, scientific notation, dense results tables, and responsive layouts.

For each direction, provide:
1. Concept name and short rationale.
2. Mood and brand attributes.
3. Color roles with contrast measurements.
4. English and Arabic type pairing.
5. Logo concept and small-size/monochrome behavior.
6. Representative desktop screen.
7. Streamlit feasibility notes.
8. Risks or tradeoffs.

Stop after Phase 1 and ask me to select a direction before creating the full system or editing implementation files.
```

**Target:** Claude Design or Manus AI. The prompt is structured for a long-context design agent and includes an explicit review checkpoint before full execution.

**Agentic safety note:** If the target tool can edit files or run commands, restrict it to design artifacts or explicitly approved frontend files. It must ask before deleting files, adding dependencies, changing the backend, modifying calculation logic, or publishing anything.

---

## 28. Final Instruction to the Design AI

The most important design problem is not making ShieldLab look “modern.” It is making a complex safety decision feel clear, trustworthy, and actionable without hiding evidence or uncertainty. Create visual interest through identity, hierarchy, interaction, and data design. Never trade legibility or safety meaning for decoration.

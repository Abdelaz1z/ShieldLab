# Physics validation before design use

Software regression checks are not a qualified expert sign-off.

- [ ] Independently check CT air kerma, transmission and required thickness against scanner isodose/survey data for head/body, each operating potential and complete weekly DLP. Record tolerances and uncertainty. The upper-table kVp route remains a REVIEW approximation.
- [ ] Independently verify the corrected NCRP 147 B.1/C.1 transcriptions, units and material basis. `tests/test_archer_reference_anchors.py` covers selected numerical anchors and the CT approximation end to end.
- [ ] Validate mixed-material layer order, spectra and scatter with measurements or an appropriate transport calculation. The product approximation has no established universal conservative bound and remains REVIEW.
- [ ] Validate drawn-room paths through several barriers, around re-entrant corners and through openings more shielding than their surrounding walls. `tests/test_drawn_survey.py` withholds compliance for these paths and checks that numerical failures remain failures; it does not validate a transport model.
- [ ] Before adding build-up coefficients, verify energy, response quantity, geometry, source and optical-depth coverage. `tests/test_buildup_validation.py` rejects legacy, malformed and out-of-range inputs. Correction tables remain REVIEW.
- [ ] Confirm product density, composition, voids and lead equivalence against supplier data. `tools/build_mu_rho.py --verify` only compares selected tabulated coefficients; `tests/test_buildup_validation.py` also checks sparse-grid exclusions near absorption edges.
- [ ] Confirm project workload, protected-point distances, occupancy, approved design goals and penetrations; obtain qualified expert review and a post-construction radiation survey.

Relevant regressions: `tests/test_broad_beam_fidelity.py` (wall segmentation and CT routing), `tests/test_model_review.py` (UI and HTML/PDF review status), and `tests/test_material_data_paths.py` (availability).

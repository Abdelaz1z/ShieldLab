"""The transmitted dose must not come out lower than the referenced method gives.

Covers audit findings F-01 (a wall's answer depending on how it was typed) and F-02
(narrow-beam physics standing in for broad-beam, including for every CT room).
"""

from __future__ import annotations

import pytest

from shieldlab.physics import barriers as ba
from shieldlab.physics import beams as bm
from shieldlab.physics import sources as src
from shieldlab.physics import transmission as tx

DIAGNOSTIC = bm.Beam(kind=bm.KIND_DIAGNOSTIC, component="secondary", kvp=120)
MEGAVOLTAGE = bm.Beam(kind=bm.KIND_MEGAVOLTAGE, component="primary", mv_energy="6 MV")


def _barrier(*layers) -> ba.Barrier:
    return ba.Barrier([ba.Layer(material, thickness) for material, thickness in layers])


# --- F-01: one wall, one answer ---------------------------------------------

@pytest.mark.parametrize("material,total_mm", [("concrete", 300.0), ("lead", 3.0),
                                               ("steel", 40.0), ("gypsum", 60.0)])
@pytest.mark.parametrize("splits", [1, 2, 3, 5])
def test_splitting_a_wall_does_not_change_its_transmission(material, total_mm, splits):
    """3 x 100 mm of concrete is the same wall as 1 x 300 mm and must agree."""
    whole = _barrier((material, total_mm))
    split = _barrier(*[(material, total_mm / splits)] * splits)
    assert split.transmission(DIAGNOSTIC) == pytest.approx(
        whole.transmission(DIAGNOSTIC), rel=1e-9
    )


def test_merge_preserves_total_thickness_and_areal_load():
    barrier = _barrier(("concrete", 100.0), ("concrete", 200.0), ("lead", 2.0))
    merged = barrier.merge_adjacent()
    assert [layer.material for layer in merged.layers] == ["concrete", "lead"]
    assert merged.total_thickness_mm() == barrier.total_thickness_mm()
    assert merged.areal_density_kg_m2() == pytest.approx(barrier.areal_density_kg_m2())


def test_a_real_sandwich_is_not_collapsed():
    """concrete/lead/concrete is a genuine build-up, not a mis-entered single wall."""
    barrier = _barrier(("concrete", 100.0), ("lead", 2.0), ("concrete", 100.0))
    assert len(barrier.merge_adjacent().layers) == 3
    assert not barrier.was_merged()


@pytest.mark.parametrize("zero_layers", [
    [("lead", 0.0)],
    [("lead", 0.0), ("steel", 0.0)],
])
def test_zero_thickness_separators_do_not_change_wall_dose(zero_layers):
    # PR #1 review: a zero-mm insert prevented two concrete courses from merging.
    whole = _barrier(("concrete", 300.0))
    split = _barrier(("concrete", 100.0), *zero_layers, ("concrete", 200.0))
    assert split.transmission(DIAGNOSTIC) == pytest.approx(whole.transmission(DIAGNOSTIC))
    assert split.merge_adjacent().areal_density_kg_m2() == whole.areal_density_kg_m2()


def test_added_concrete_matches_a_single_finished_wall():
    from shieldlab.physics import solver
    from shieldlab.regulatory import limits as reg

    source = src.ct_source([src.CTExamWorkload("body_average", 550, 150)], 3)
    goal = reg.design_goal("NCRP", "uncontrolled")
    existing = _barrier(("concrete", 50), ("lead", 0))
    added = solver.required_thickness(source, "concrete", goal, existing=existing)
    whole = solver.required_thickness(source, "concrete", goal)
    assert added + 50 == pytest.approx(whole, abs=0.002)


def test_was_merged_flags_only_split_walls():
    assert _barrier(("concrete", 150.0), ("concrete", 150.0)).was_merged()
    assert not _barrier(("concrete", 150.0), ("lead", 2.0)).was_merged()


def test_tvl_models_are_unaffected_by_splitting():
    """B = 10^(-x/TVL) is a pure exponential, so the product was always exact here."""
    whole = _barrier(("concrete", 300.0))
    split = _barrier(("concrete", 100.0), ("concrete", 100.0), ("concrete", 100.0))
    assert split.transmission(MEGAVOLTAGE) == pytest.approx(
        whole.transmission(MEGAVOLTAGE), rel=1e-12
    )


# --- F-02: CT is shielded broad-beam ----------------------------------------

def test_ct_scatter_uses_broad_beam_transmission():
    source = src.ct_source([src.CTExamWorkload("body_average", 550.0, 150.0)], 3.0)
    for component in source.components:
        assert component.beam.kind == bm.KIND_DIAGNOSTIC
        assert component.beam.component == "secondary"
        assert bm.data_path(component.beam, "concrete") == bm.PATH_BROAD


@pytest.mark.parametrize("kvp,table_kvp", [(80, 100), (100, 100), (120, 125), (140, 150)])
def test_ct_scanner_potential_selects_the_upper_dataset(kvp, table_kvp):
    source = src.ct_source([src.CTExamWorkload("head", 1200.0, 30.0)], 2.0, kvp=kvp)
    tabulated = bm.Beam(kind=bm.KIND_DIAGNOSTIC, component="secondary", kvp=table_kvp)
    for material, thickness in [("lead", 2), ("concrete", 200)]:
        actual = ba.Barrier().add(material, thickness).transmission(source.components[0].beam)
        expected = bm.transmission_of_layer(tabulated, material, thickness)
        assert actual == pytest.approx(expected)
    assert f"table {table_kvp} kVp" in source.notes[-1]


@pytest.mark.parametrize("kvp", [0, 29, 151, float("nan"), float("inf")])
def test_ct_outside_transmission_table_range_is_rejected(kvp):
    with pytest.raises(ValueError, match="kVp must be within"):
        src.ct_source([src.CTExamWorkload("head", 1200, 30)], 2, kvp=kvp)


@pytest.mark.parametrize("material,thickness", [("concrete", 150.0), ("concrete", 200.0),
                                                ("lead", 2.0), ("lead", 3.0)])
def test_ct_reports_more_dose_than_the_old_narrow_beam_model(material, thickness):
    """The re-route must move the answer toward MORE transmitted dose, never less."""
    narrow = bm.Beam(kind=bm.KIND_MONO, mono_energy_MeV=0.07)
    ct = src.ct_source([src.CTExamWorkload("head", 1200.0, 30.0)], 2.0).components[0].beam
    assert (bm.transmission_of_layer(ct, material, thickness)
            > bm.transmission_of_layer(narrow, material, thickness))


# --- F-02: the build-up hook is real ----------------------------------------

def test_narrow_beam_model_is_declared_not_silently_applied():
    """No material ships build-up data yet, so each must report itself narrow-beam."""
    beam = bm.Beam(kind=bm.KIND_MONO, mono_energy_MeV=0.2)
    for material in ("barite_concrete", "brick", "lead_glass", "water"):
        assert not bm.has_buildup_data(material, 0.2)
        assert bm.data_path(beam, material) == bm.PATH_NARROW


def test_buildup_interpolation_rejects_extrapolation():
    mux, factors = [0.0, 5.0, 10.0], [1.0, 8.0, 20.0]
    assert tx.interp_buildup(0, mux, factors) == 1
    assert tx.interp_buildup(10, mux, factors) == 20
    assert tx.interp_buildup(3, mux, factors) == pytest.approx(5.2)
    with pytest.raises(ValueError, match="outside"):
        tx.interp_buildup(50, mux, factors)


def test_supplying_buildup_data_raises_dose_but_does_not_establish_broad_beam_validity(monkeypatch):
    """Synthetic JSON input tests the correction mechanism, not physical accuracy."""
    from shieldlab import data_loader as dl

    materials = dl.materials()
    entry = dict(materials["materials"]["brick"])
    entry["buildup_tables"] = [{
        "energy_MeV": 0.364, "quantity": "air_kerma",
        "geometry": "synthetic test geometry", "ref": "synthetic test only",
        "mux": [0, 0.5, 1, 2, 4, 7, 10], "B": [1, 1.4, 2, 3.3, 6.4, 12, 18],
    }]
    patched = {**materials, "materials": {**materials["materials"], "brick": entry}}
    monkeypatch.setattr(dl, "materials", lambda: patched)

    beam = bm.Beam(kind=bm.KIND_MONO, mono_energy_MeV=0.364)
    assert bm.has_buildup_data("brick", 0.364)
    assert not bm.has_buildup_data("brick", 0.140)
    assert bm.data_path(beam, "brick") == bm.PATH_BUILDUP
    assert bm.data_path(bm.Beam(kind=bm.KIND_MONO, mono_energy_MeV=0.140), "brick") == bm.PATH_NARROW

    with_buildup = bm.transmission_of_layer(beam, "brick", 300.0)
    narrow = tx.mu_buildup_transmission(300.0, *bm._mono_params(beam, "brick"), 1.0)
    assert with_buildup > narrow, "a build-up table must raise the transmitted dose"

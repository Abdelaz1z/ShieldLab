"""Malformed or unqualified build-up data must fail explicitly."""

import pytest

from shieldlab import data_loader as dl
from shieldlab.physics import beams as bm, transmission as tx


@pytest.mark.parametrize("depths,factors", [
    ([], []), ([0, 1], [1]), ([1, 2], [1, 2]),
    ([0, 0], [1, 2]), ([0, -1], [1, 2]),
    ([0, 1], [1, 0.5]), ([0, 1], [1, float("nan")]),
    ([0, float("inf")], [1, 2]),
    (None, [1, 2]), ([0, 1], [1, "invalid"]),
])
def test_malformed_buildup_grid_is_rejected(depths, factors):
    with pytest.raises(ValueError, match="Build-up"):
        tx.interp_buildup(0.5, depths, factors)


def test_legacy_arrays_cannot_silently_claim_broad_beam_support(monkeypatch):
    materials = dl.materials()
    brick = {**materials["materials"]["brick"], "buildup_mux": [0, 1], "buildup_B": [1, 2]}
    # materials() is the JSON input boundary; no internal physics is mocked.
    monkeypatch.setattr(dl, "materials", lambda: {
        **materials, "materials": {**materials["materials"], "brick": brick},
    })
    beam = bm.Beam(kind=bm.KIND_MONO, mono_energy_MeV=0.364)
    with pytest.raises(ValueError, match="lack energy and geometry"):
        bm.data_path(beam, "brick")
    with pytest.raises(ValueError, match="lack energy and geometry"):
        bm.transmission_of_layer(beam, "brick", 100)


@pytest.mark.parametrize("material,energy", [
    ("lead", 0.09), ("lead", 0.012), ("lead_glass", 0.09),
    ("barite_concrete", 0.04), ("brick", 0.9), ("brick", 0.001),
])
def test_sparse_grid_gaps_are_unavailable_in_lookup_and_evaluation(material, energy):
    beam = bm.Beam(kind=bm.KIND_MONO, mono_energy_MeV=energy)
    assert bm.data_path(beam, material) is bm.PATH_NONE
    assert material not in bm.available_materials(beam)
    with pytest.raises(ValueError, match="No mu/rho data"):
        bm.transmission_of_layer(beam, material, 10)


@pytest.mark.parametrize("factor", [0.5, float("nan"), float("inf")])
def test_invalid_explicit_buildup_cannot_lower_dose(factor):
    with pytest.raises(ValueError, match="Build-up factor"):
        tx.mu_buildup_transmission(100, 0.2, 2350, factor)


@pytest.mark.parametrize("missing_field", ["energy_MeV", "quantity", "geometry", "ref"])
def test_unqualified_buildup_record_is_rejected(monkeypatch, missing_field):
    materials = dl.materials()
    table = dict(energy_MeV=.364, quantity="air_kerma", geometry="test only",
                 ref="synthetic test", mux=[0, 10], B=[1, 5])
    del table[missing_field]
    brick = {**materials["materials"]["brick"], "buildup_tables": [table]}
    monkeypatch.setattr(dl, "materials", lambda: {
        **materials, "materials": {**materials["materials"], "brick": brick},
    })
    beam = bm.Beam(kind=bm.KIND_MONO, mono_energy_MeV=.364)
    with pytest.raises(ValueError, match="require energy"):
        bm.transmission_of_layer(beam, "brick", 100)

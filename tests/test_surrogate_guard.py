"""Direct coverage for the guard that decides whether an ML prediction is trusted.

Audit finding F-09. surrogate_guard was the least-covered module in the engine at
40%, and it is the component that decides whether a surrogate prediction is used at
all or replaced by the analytical fallback. It was reached only by unpickling the
deployed bundle, so its own logic was never exercised against a known domain.

These build a small synthetic training domain instead, so each rule can be checked
on inputs whose correct answer is known by construction.
"""

from __future__ import annotations

import numpy as np
import pytest

from shieldlab.room.surrogate_guard import (
    ExcisedRegion,
    TrainingDomain,
    guarded_predict,
)

FEATURES = ["primary_energy_keV", "thickness_mm", "density_gcm3"]


@pytest.fixture
def domain():
    """A dense, well-sampled cube of training points."""
    rng = np.random.default_rng(20260830)
    training = np.column_stack([
        rng.uniform(100.0, 600.0, 400),      # energy
        rng.uniform(50.0, 400.0, 400),       # thickness
        rng.uniform(1.5, 4.0, 400),          # density
    ])
    return TrainingDomain(FEATURES, k=8, q=0.99).fit(training)


def test_a_point_inside_the_cloud_is_in_domain(domain):
    assert domain.in_domain(np.array([[350.0, 200.0, 2.4]]))[0]


@pytest.mark.parametrize("query", [
    [1500.0, 200.0, 2.4],     # energy far above the box
    [350.0, 5000.0, 2.4],     # thickness far above the box
    [350.0, 200.0, 0.1],      # density far below the box
])
def test_points_outside_the_box_are_rejected(domain, query):
    assert not domain.in_box(np.array([query]))[0]
    assert not domain.in_domain(np.array([query]))[0]


def test_the_density_test_catches_an_empty_corner_inside_the_box():
    """The weakness the kNN test exists to close: in the box, but with no neighbours."""
    cluster = np.column_stack([
        np.random.default_rng(7).uniform(100.0, 200.0, 300),
        np.random.default_rng(8).uniform(50.0, 100.0, 300),
        np.random.default_rng(9).uniform(1.5, 2.0, 300),
    ])
    # One far-off point stretches the box without populating the space between.
    training = np.vstack([cluster, [[600.0, 400.0, 4.0]]])
    domain = TrainingDomain(FEATURES, k=8, q=0.99).fit(training)

    corner = np.array([[590.0, 390.0, 3.9]])
    assert domain.in_box(corner)[0], "the corner is inside the axis-aligned box"
    assert not domain.in_density(corner)[0], "but it has no nearby training data"
    assert not domain.in_domain(corner)[0]


def test_excised_rows_are_flagged_by_construction(domain):
    """Every excised configuration is nearer to itself than to any retained row."""
    excised = np.array([[550.0, 380.0, 3.8], [120.0, 60.0, 1.6]])
    region = ExcisedRegion(domain).fit(excised)
    assert region.near_excised(excised).all()


def test_a_point_far_from_excised_rows_is_not_flagged(domain):
    region = ExcisedRegion(domain).fit(np.array([[550.0, 380.0, 3.8]]))
    assert not region.near_excised(np.array([[300.0, 150.0, 2.0]]))[0]


def test_report_names_every_feature_and_the_knn_settings(domain):
    report = domain.report()
    assert set(FEATURES) <= set(report)
    assert report["_knn"]["k"] == 8 and report["_knn"]["quantile"] == 0.99
    assert report["_knn"]["threshold_std"] is not None
    for feature in FEATURES:
        low, high = report[feature]
        assert low < high


# --- guarded_predict: the routing decision itself ---------------------------

class _ConstantModel:
    """Stands in for the tree ensemble: returns the same value for every row."""

    def __init__(self, value=-2.0):
        self.value = value

    def predict(self, X):
        return np.full(len(np.atleast_2d(X)), self.value)


def test_in_domain_rows_keep_the_surrogate_value(domain):
    predictions, ood = guarded_predict(
        _ConstantModel(-2.0), domain, np.array([[350.0, 200.0, 2.4]]),
        analytical_fn=lambda row: -9.0,
    )
    assert not ood[0]
    assert predictions[0] == pytest.approx(-2.0)


def test_out_of_domain_rows_fall_back_to_the_analytical_value(domain):
    """A tree ensemble flat-lines outside its training box; the fallback must win."""
    predictions, ood = guarded_predict(
        _ConstantModel(-2.0), domain, np.array([[9000.0, 200.0, 2.4]]),
        analytical_fn=lambda row: -9.0,
    )
    assert ood[0]
    assert predictions[0] == pytest.approx(-9.0)


def test_out_of_domain_is_still_flagged_without_a_fallback(domain):
    predictions, ood = guarded_predict(
        _ConstantModel(-2.0), domain, np.array([[9000.0, 200.0, 2.4]]),
    )
    assert ood[0], "with no analytical_fn the value stands, but must not be silent"
    assert predictions[0] == pytest.approx(-2.0)


def test_excised_proximity_alone_forces_the_fallback(domain):
    """A row can pass box and density and still be untrusted."""
    query = np.array([[550.0, 380.0, 3.8]])
    assert domain.in_domain(query)[0], "this row passes the box and density tests"

    region = ExcisedRegion(domain).fit(query)
    predictions, ood = guarded_predict(
        _ConstantModel(-2.0), domain, query,
        analytical_fn=lambda row: -9.0, excised=region,
    )
    assert ood[0]
    assert predictions[0] == pytest.approx(-9.0)


def test_a_mixed_batch_routes_each_row_independently(domain):
    batch = np.array([
        [350.0, 200.0, 2.4],      # in domain
        [9000.0, 200.0, 2.4],     # outside the box
        [300.0, 150.0, 2.0],      # in domain
    ])
    predictions, ood = guarded_predict(
        _ConstantModel(-2.0), domain, batch, analytical_fn=lambda row: -9.0,
    )
    assert list(ood) == [False, True, False]
    assert list(predictions) == pytest.approx([-2.0, -9.0, -2.0])

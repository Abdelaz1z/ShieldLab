"""
surrogate_guard.py
==================
Safety guard for the shielding surrogate (review items W11 + reviewer-weakness #9). Tree ensembles
(RF/GBR) CANNOT extrapolate: outside the training domain they flat-line at a boundary leaf value,
which in some directions UNDER-predicts transmission (-> under-predicts dose -> non-conservative).

Design rule: the surrogate is trusted ONLY for INTERPOLATION. A query is in-domain only if it is
BOTH (a) inside the per-feature [min,max] box AND (b) in a DENSE region of training data — i.e. its
distance to the k-th nearest training point (in standardized feature space) is within the training
distribution. (b) closes the weakness that a point can sit inside the axis-aligned box yet in an
empty corner with no nearby training data (false confidence). OOD queries fall back to the
conservative analytical value (ShieldLab/NCRP), never the flat-lined tree output.
"""
from __future__ import annotations

import numpy as np

try:
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler
    _HAVE_SK = True
except Exception:                       # guard still works as a pure box without sklearn
    _HAVE_SK = False


class TrainingDomain:
    """Per-feature [min,max] box PLUS a kNN-distance density test for honest OOD detection."""

    def __init__(self, feature_names, k=8, q=0.99):
        self.features = list(feature_names)
        self.k = k                      # neighbours for the density test
        self.q = q                      # training-distance quantile used as the OOD threshold
        self.lo = self.hi = None
        self._scaler = self._nn = self._thr = None

    def fit(self, X):
        X = np.asarray(X, float)
        self.lo, self.hi = X.min(axis=0), X.max(axis=0)
        if _HAVE_SK and len(X) > self.k + 1:
            self._scaler = StandardScaler().fit(X)
            Xs = self._scaler.transform(X)
            self._nn = NearestNeighbors(n_neighbors=self.k + 1).fit(Xs)
            d, _ = self._nn.kneighbors(Xs, n_neighbors=self.k + 1)   # col 0 = self (dist 0)
            kth = d[:, self.k]                                       # k-th nearest OTHER point
            self._thr = float(np.quantile(kth, self.q))             # OOD threshold
        return self

    def in_box(self, X):
        X = np.asarray(X, float)
        return np.all((X >= self.lo) & (X <= self.hi), axis=1)

    def in_density(self, X):
        """True where the k-th nearest training point is within the training kNN-distance threshold."""
        if self._nn is None:
            return np.ones(len(np.atleast_2d(np.asarray(X, float))), dtype=bool)
        Xs = self._scaler.transform(np.asarray(X, float))
        d, _ = self._nn.kneighbors(Xs, n_neighbors=self.k)          # new query: no self to drop
        return d[:, self.k - 1] <= self._thr

    def in_domain(self, X):
        """Interpolation region: inside the box AND in a dense (well-sampled) neighbourhood."""
        return self.in_box(X) & self.in_density(X)

    def report(self):
        r = {f: [float(lo), float(hi)] for f, lo, hi in zip(self.features, self.lo, self.hi)}
        r["_knn"] = {"k": self.k, "quantile": self.q,
                     "threshold_std": (None if self._thr is None else round(self._thr, 4))}
        return r


class ExcisedRegion:
    """Proximity test against rows EXCISED from training (deep-tail + off-axis-shadow estimator-bias
    regions; see PAPER_A_DRAFT.md §6.3, fix_deep_tail.py, apply_offaxis_exclusion.py).

    The box + density tests alone CANNOT protect these regions: they sit inside the feature box and
    next to retained training data, so a tree ensemble would silently extrapolate across them. The
    rule here is support-based and symmetric: a query is untrusted if it lies CLOSER to removed
    support than to retained support — i.e. its nearest excised row (standardized space) is nearer
    than its nearest trusted training row. Every excised configuration itself is flagged by
    construction (distance 0 to itself, positive to all trusted rows), and the rule generalizes
    automatically to any future excision: refit on the new excised set, nothing else changes."""

    def __init__(self, domain: "TrainingDomain"):
        self.domain = domain
        self._nn_exc = None

    def fit(self, X_excised):
        X_excised = np.atleast_2d(np.asarray(X_excised, float))
        if _HAVE_SK and self.domain._scaler is not None and len(X_excised):
            Xs = self.domain._scaler.transform(X_excised)
            self._nn_exc = NearestNeighbors(n_neighbors=1).fit(Xs)
        return self

    def near_excised(self, X):
        """True where the query is closer to the nearest excised row than to the nearest trusted
        training row (both in the domain's standardized space)."""
        if self._nn_exc is None or self.domain._nn is None:
            return np.zeros(len(np.atleast_2d(np.asarray(X, float))), dtype=bool)
        Xs = self.domain._scaler.transform(np.asarray(X, float))
        d_exc, _ = self._nn_exc.kneighbors(Xs, n_neighbors=1)
        d_tr, _ = self.domain._nn.kneighbors(Xs, n_neighbors=1)
        return d_exc[:, 0] < d_tr[:, 0]


def guarded_predict(model, domain, X, analytical_fn=None, excised: "ExcisedRegion | None" = None):
    """Predict in-domain with the surrogate; OOD rows -> conservative analytical value (if given),
    else the model value but flagged. Returns (predictions, ood_mask). OOD = outside the box
    OR in a sparse region (kNN-distance test) OR nearer to an excised estimator-bias row than to
    retained training support (ExcisedRegion proximity test)."""
    X = np.asarray(X, float)
    pred = np.asarray(model.predict(X), float)
    ood = ~domain.in_domain(X)
    if excised is not None:
        ood |= excised.near_excised(X)
    if analytical_fn is not None and ood.any():
        for i in np.where(ood)[0]:
            pred[i] = float(analytical_fn(X[i]))
    return pred, ood

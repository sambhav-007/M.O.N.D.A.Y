"""
Validates M.O.N.D.A.Y. Component 2.6's closed-form Shapley implementation
against the reference `shap.LinearExplainer`.

Runs in an isolated venv (numba 0.61.2 + shap 0.52.0), because shap cannot be
installed in the project environment. Imports the ACTUAL shipping functions from
ml/xai_explainer.py -- not a reimplementation -- so this validates the code that
really runs.

Exit code 0 = equivalent within tolerance.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(r"D:\work\M.O.N.D.A.Y")
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import shap
from sklearn.linear_model import LinearRegression, LogisticRegression

from ml.xai_explainer import exact_linear_shap_values, linear_shap_base_value

TOL = 1e-10
results = []


def report(name, ours, theirs, extra=""):
    ours = np.asarray(ours, dtype=float)
    theirs = np.asarray(theirs, dtype=float)
    if ours.shape != theirs.shape:
        print(f"  SHAPE MISMATCH {name}: ours {ours.shape} vs shap {theirs.shape}")
        results.append((name, float("inf"), ours.shape, theirs.shape))
        return
    dev = float(np.max(np.abs(ours - theirs)))
    scale = float(np.max(np.abs(theirs))) or 1.0
    verdict = "MATCH" if dev <= TOL else "DIFFER"
    print(f"  [{verdict}] {name}")
    print(f"          max |ours - shap| = {dev:.3e}   (values up to {scale:.3f}) {extra}")
    results.append((name, dev, ours.shape, theirs.shape))


print("=" * 78)
print("Closed-form Shapley  vs  shap.LinearExplainer (interventional)")
print(f"shap {shap.__version__} | numpy {np.__version__} | tolerance {TOL:.0e}")
print("=" * 78)

# ── Case 1: Multiple Linear Regression (mirrors Component 2.2) ──────────────
print("\nCase 1 - Linear Regression, 15 dense features (Component 2.2 shape)")
rng = np.random.default_rng(42)
n, p = 800, 15
X = rng.normal(size=(n, p))
X[:, :6] = (rng.random((n, 6)) < 0.3).astype(float)   # one-hot-ish task dummies
X[:, 6:11] = (rng.random((n, 5)) < 0.25).astype(float)  # agent dummies
beta = rng.normal(scale=2.0, size=p)
y = X @ beta + rng.normal(scale=0.5, size=n)

lr = LinearRegression().fit(X, y)
bg_mean = X.mean(axis=0)
X_explain = X[:200]

ours = exact_linear_shap_values(lr.coef_, X_explain, bg_mean)
ours_base = linear_shap_base_value(lr.intercept_, lr.coef_, bg_mean)

# shap's Independent masker subsamples the background to 100 rows by default,
# which changes E[x] and would make this a comparison of two different
# background distributions rather than of two algorithms. Use every row.
masker = shap.maskers.Independent(X, max_samples=X.shape[0])
ex = shap.LinearExplainer(lr, masker, feature_perturbation="interventional")
theirs = ex.shap_values(X_explain)

report("regression shap_values", ours, theirs)
report("regression base_value", np.ravel(ours_base), np.ravel(ex.expected_value))

# ── Case 2: Multiclass Logistic Regression (mirrors Component 2.1) ──────────
print("\nCase 2 - Multiclass Logistic Regression, 40 features / 6 classes")
n, p, k = 1200, 40, 6
Xc = np.abs(rng.normal(size=(n, p))) * (rng.random((n, p)) < 0.2)  # sparse, TF-IDF-like
W = rng.normal(size=(p, k))
yc = np.argmax(Xc @ W + rng.normal(scale=0.3, size=(n, k)), axis=1)

clf = LogisticRegression(max_iter=2000).fit(Xc, yc)
bg_mean_c = Xc.mean(axis=0)
Xc_explain = Xc[:150]

ours_c = exact_linear_shap_values(clf.coef_, Xc_explain, bg_mean_c)
ours_base_c = linear_shap_base_value(clf.intercept_, clf.coef_, bg_mean_c)

masker_c = shap.maskers.Independent(Xc, max_samples=Xc.shape[0])
ex_c = shap.LinearExplainer(clf, masker_c, feature_perturbation="interventional")
theirs_c = ex_c.shap_values(Xc_explain)
theirs_c = np.asarray(theirs_c)

# shap may return (n_classes, n_samples, n_features) or (n_samples, n_features, n_classes)
if theirs_c.shape != ours_c.shape and theirs_c.shape == (k, Xc_explain.shape[0], p):
    theirs_c = np.transpose(theirs_c, (1, 2, 0))
    note = "(shap output transposed to (samples, features, classes))"
else:
    note = ""

report("multiclass shap_values", ours_c, theirs_c, note)
report("multiclass base_value", np.ravel(ours_base_c), np.ravel(ex_c.expected_value))

# ── Case 3: local accuracy on both ─────────────────────────────────────────
print("\nCase 3 - Local accuracy axiom  (sum(phi) + phi_0 == f(x))")
recon_r = ours.sum(axis=1) + ours_base
dev_r = float(np.max(np.abs(recon_r - lr.predict(X_explain))))
print(f"  regression : max |sum(phi) + phi_0 - f(x)| = {dev_r:.3e}")

recon_c = ours_c.sum(axis=1) + np.ravel(ours_base_c)[None, :]
dev_c = float(np.max(np.abs(recon_c - clf.decision_function(Xc_explain))))
print(f"  multiclass : max |sum(phi) + phi_0 - f(x)| = {dev_c:.3e}")
results.append(("local accuracy (regression)", dev_r, None, None))
results.append(("local accuracy (multiclass)", dev_c, None, None))

# ── Verdict ────────────────────────────────────────────────────────────────
print("\n" + "=" * 78)
worst = max(r[1] for r in results)
print(f"Worst deviation across all checks: {worst:.3e}")
if worst <= TOL:
    print("VERDICT: EQUIVALENT - closed form matches shap.LinearExplainer.")
    sys.exit(0)
print("VERDICT: MISMATCH - investigate before shipping.")
sys.exit(1)

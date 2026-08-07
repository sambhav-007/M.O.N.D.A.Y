# Component 2.6 — Validation of the Closed-Form Shapley Implementation

**Course**: 24CSE0316 · **CLO**: CLO02 / CLO06 (beyond-syllabus) · **Date**: 2026-08-06

This document establishes that M.O.N.D.A.Y.'s XAI layer computes *exact* Shapley
values, and that it agrees with the reference `shap` library it replaces.

---

## 1. Why the `shap` library is not used

`shap` cannot be installed in the project environment. It hard-imports `numba` at
package load (`shap/utils/_clustering.py` → `from numba import njit`), and no
numba release satisfies this project's constraints:

| numba | llvmlite | Smart App Control | numpy pin | Consequence |
|-------|----------|-------------------|-----------|-------------|
| 0.66.0 | 0.48.0 | **Blocked** — `DLL load failed while importing _typeconv: An Application Control policy has blocked this file` | `numpy>=2.3.5` OK | Cannot import |
| 0.61.2 | 0.44.0 | Loads | `numpy<2.2` | Breaks `mlxtend` 0.25.0 (needs `numpy>=2.3.5`) → **breaks Component 2.4** |

Windows Smart App Control blocks binaries by *reputation*, which is the same
mechanism that blocked `pandas` 3.0.5 earlier in this project. It is a system
security setting and a one-way switch — re-enabling it requires resetting
Windows — so disabling it was out of scope.

Rather than drop the component or downgrade the CLO06 claim, the Shapley values
are computed directly. For these two models that is not a compromise: it is
exact.

## 2. The mathematics

Both explained models are **linear**:

- Component 2.1 — Logistic Regression over TF-IDF features
- Component 2.2 — Multiple Linear Regression over engineered features

For a linear model $f(x) = b + \sum_j \beta_j x_j$, the Shapley value of feature
$j$ under interventional (marginal) perturbation against background distribution
$D$ has the closed form

$$\phi_j(x) = \beta_j\,\bigl(x_j - \mathbb{E}_D[x_j]\bigr)$$

with base value

$$\phi_0 = \mathbb{E}_D[f(x)] = b + \sum_j \beta_j\,\mathbb{E}_D[x_j]$$

Because the model is additive, feature independence — the assumption that makes
this closed form valid — is exactly the assumption `shap.LinearExplainer` makes
under `feature_perturbation="interventional"`. The two are therefore the same
computation, not an approximation of one another.

Implementation: `ml/xai_explainer.py` → `exact_linear_shap_values()`,
`linear_shap_base_value()`.

## 3. Validation procedure

`reports/2_6_validate_shap_equivalence.py` imports **the actual shipping
functions** from `ml/xai_explainer.py` (not a reimplementation) and compares them
against `shap.LinearExplainer` on two models matching the shapes of Components
2.1 and 2.2.

Because `shap` cannot be installed in the project environment, the script runs in
an **isolated throwaway venv** with `numba==0.61.2` + `shap==0.52.0`, where the
numpy pin is harmless because `mlxtend` is not present. The project environment
was left untouched.

```bash
py -3.12 -m venv shapvenv
shapvenv/Scripts/python -m pip install "numba==0.61.2" "shap==0.52.0" scikit-learn rich
shapvenv/Scripts/python reports/2_6_validate_shap_equivalence.py
```

> **One methodological note.** `shap`'s `Independent` masker subsamples the
> background to 100 rows by default. On the first run this produced deviations of
> ~1e-1 — not an algorithmic disagreement but a comparison of two *different*
> background distributions, since $\mathbb{E}_D[x_j]$ differed between the two
> sides. Passing `max_samples=X.shape[0]` makes the backgrounds identical. This
> is worth stating because it is exactly the kind of difference that could be
> mistaken for a bug, or hidden by a loose tolerance.

## 4. Result

```
Closed-form Shapley  vs  shap.LinearExplainer (interventional)
shap 0.52.0 | numpy 2.2.6 | tolerance 1e-10

Case 1 - Linear Regression, 15 dense features (Component 2.2 shape)
  [MATCH] regression shap_values
          max |ours - shap| = 0.000e+00   (values up to 7.839)
  [MATCH] regression base_value
          max |ours - shap| = 0.000e+00   (values up to 2.293)

Case 2 - Multiclass Logistic Regression, 40 features / 6 classes
  [MATCH] multiclass shap_values
          max |ours - shap| = 0.000e+00   (values up to 9.505)
  [MATCH] multiclass base_value
          max |ours - shap| = 0.000e+00   (values up to 1.137)

Case 3 - Local accuracy axiom  (sum(phi) + phi_0 == f(x))
  regression : max |sum(phi) + phi_0 - f(x)| = 3.553e-15
  multiclass : max |sum(phi) + phi_0 - f(x)| = 8.882e-15

Worst deviation across all checks: 8.882e-15
VERDICT: EQUIVALENT - closed form matches shap.LinearExplainer.
```

**The Shapley values are bit-for-bit identical** (`0.000e+00`), for both the
regression and the multiclass classifier, for both the attributions and the base
value. The only non-zero figures are the local-accuracy residuals at ~1e-15,
which is float64 rounding.

## 5. Runtime self-check

Equivalence to a reference library is a one-off argument. To make every
explanation self-verifying, `check_local_accuracy()` enforces the Shapley
efficiency axiom on **every** explanation the system produces:

$$\sum_j \phi_j(x) + \phi_0 = f(x)$$

If the identity does not hold to 1e-8, the code **raises** rather than returning a
plausible-looking number. Observed in the live component run:

| Model | max \|Σφ + φ₀ − f(x)\| |
|-------|------------------------|
| Intent Classifier (2.1), 100 samples, 2402 TF-IDF features, 7 classes | 1.64e-14 |
| ETA Regressor (2.2), 200 samples, 15 features | 1.14e-13 |

## 6. Evidence produced

| Artefact | Content |
|----------|---------|
| `reports/2_6_xai_intent_top_features.csv` | Top-8 attributed tokens per intent class |
| `reports/2_6_xai_eta_feature_importance.csv` | Mean \|SHAP\| and mean signed SHAP per ETA feature |
| `reports/figures/2_6_xai_intent_top_features.png` | Per-intent attribution bar charts |
| `reports/figures/2_6_xai_eta_feature_importance.png` | Global ETA feature attribution |
| `reports/figures/2_6_xai_single_prediction.png` | Single-prediction breakdown behind a Tier-2 ETA |
| `reports/2_6_validate_shap_equivalence.py` | The validation script itself, rerunnable |

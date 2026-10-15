"""Small, deterministic forecasting models and auditable uncertainty estimates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from wardcast.features import FEATURE_COLUMNS, FEATURE_LABELS

MODELS = ("persistence", "seasonal_naive", "trailing_mean", "ridge", "lightgbm")
NOMINAL_COVERAGE = 0.8


def baseline_predictions(frame: pd.DataFrame, method: str) -> np.ndarray:
    current = frame["occupied_current"].to_numpy(dtype=float)
    if method == "persistence":
        return current
    column = {"seasonal_naive": "occupied_seasonal_target", "trailing_mean": "occupied_mean_3"}[method]
    return frame[column].fillna(frame["occupied_current"]).to_numpy(dtype=float)


@dataclass
class ForecastModel:
    name: str
    estimator: Any = None
    quantile_lower: Any = None
    quantile_upper: Any = None

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        if self.name in MODELS[:3]:
            return baseline_predictions(frame, self.name)
        delta = self.estimator.predict(frame[FEATURE_COLUMNS])
        return np.maximum(0.0, frame["occupied_current"].to_numpy(dtype=float) + delta)

    def raw_quantiles(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        current = frame["occupied_current"].to_numpy(dtype=float)
        lo = current + self.quantile_lower.predict(frame[FEATURE_COLUMNS])
        hi = current + self.quantile_upper.predict(frame[FEATURE_COLUMNS])
        point = self.predict(frame)
        return np.maximum(0, np.minimum(np.minimum(lo, hi), point)), np.maximum(np.maximum(lo, hi), point)

    def explanations(self, frame: pd.DataFrame) -> list[list[dict]]:
        """For ML models, explain the delta added to current occupied beds."""
        if self.name in MODELS[:3]:
            feature = {"persistence": "occupied_current", "seasonal_naive": "occupied_seasonal_target", "trailing_mean": "occupied_mean_3"}[self.name]
            output = []
            for _, row in frame.iterrows():
                used = feature if pd.notna(row[feature]) else "occupied_current"
                output.append([{"feature": used, "label": FEATURE_LABELS[used], "value": float(row[used]), "contribution": None}])
            return output
        if self.name == "lightgbm":
            import shap

            explainer = shap.TreeExplainer(self.estimator)
            contributions = np.asarray(explainer.shap_values(frame[FEATURE_COLUMNS]))
            intercept = float(np.asarray(explainer.expected_value).reshape(-1)[0])
        else:
            transformed = self.estimator[:-1].transform(frame[FEATURE_COLUMNS])
            contributions = transformed * self.estimator[-1].coef_
            intercept = float(self.estimator[-1].intercept_)
        output = []
        for (_, row), terms in zip(frame.iterrows(), contributions):
            order = np.argsort(np.abs(terms))[::-1][:5]
            entries = [{"feature": "occupied_current", "label": "Starting occupied beds", "value": float(row["occupied_current"]), "contribution": None},
                       {"feature": "expected_delta", "label": "Expected change before feature effects", "value": intercept, "contribution": intercept}]
            for i in order:
                value = row[FEATURE_COLUMNS[i]]
                entries.append({"feature": FEATURE_COLUMNS[i], "label": FEATURE_LABELS[FEATURE_COLUMNS[i]], "value": float(value) if pd.notna(value) else None, "contribution": float(terms[i])})
            remainder = float(terms.sum() - terms[order].sum())
            entries.append({"feature": "other_features", "label": "Other feature effects", "value": None, "contribution": remainder})
            raw_prediction = float(row["occupied_current"] + intercept + terms.sum())
            if raw_prediction < 0:
                entries.append({"feature": "nonnegative_adjustment", "label": "Nonnegative forecast adjustment", "value": None, "contribution": -raw_prediction})
            output.append(entries)
        return output


def fit_model(name: str, train: pd.DataFrame, *, quantiles: bool = True) -> ForecastModel:
    if name not in MODELS:
        raise ValueError(f"Unknown model: {name}")
    model = ForecastModel(name)
    if name in MODELS[:3]:
        return model
    if train.empty:
        raise ValueError("Cannot fit a model without observed training outcomes")
    x = train[FEATURE_COLUMNS]
    delta = train["actual"].to_numpy() - train["occupied_current"].to_numpy()
    if name == "ridge":
        model.estimator = Pipeline([
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scale", StandardScaler()),
            ("regression", Ridge(alpha=100.0)),
        ]).fit(x, delta)
    else:
        params = dict(n_estimators=100, learning_rate=0.04, num_leaves=7, max_depth=3,
                      min_child_samples=40, reg_lambda=10.0, verbosity=-1,
                      random_state=42, n_jobs=2, deterministic=True, force_col_wise=True)
        model.estimator = LGBMRegressor(objective="regression_l1", **params).fit(x, delta)
        if quantiles:
            model.quantile_lower = LGBMRegressor(objective="quantile", alpha=0.1, **params).fit(x, delta)
            model.quantile_upper = LGBMRegressor(objective="quantile", alpha=0.9, **params).fit(x, delta)
    return model


def conformal_radius(residuals: np.ndarray, coverage: float = NOMINAL_COVERAGE) -> float | None:
    """Finite-sample rank quantile; the pooled time series is not exchangeable."""
    residuals = np.asarray(residuals, dtype=float)
    residuals = residuals[np.isfinite(residuals)]
    if not len(residuals):
        return None
    rank = min(len(residuals), int(np.ceil((len(residuals) + 1) * coverage)))
    return float(np.sort(np.abs(residuals))[rank - 1])


def prediction_intervals(model: ForecastModel, frame: pd.DataFrame, residuals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    prediction = model.predict(frame)
    if model.name == "lightgbm":
        return model.raw_quantiles(frame)
    # Residuals are scaled by origin occupancy so small and large trusts do not
    # receive an identical absolute bed-count uncertainty allowance.
    radius = conformal_radius(residuals)
    if radius is None:
        raise ValueError("Intervals require prior observed residuals")
    width = radius * np.maximum(frame["occupied_current"].to_numpy(dtype=float), 1.0)
    return np.maximum(0, prediction - width), prediction + width


def metrics(frame: pd.DataFrame) -> dict:
    valid = frame.loc[frame["actual"].notna()].copy()
    if valid.empty:
        return {"mae": None, "wape": None, "coverage": None, "mean_interval_width": None, "n": 0}
    error = np.abs(valid["actual"] - valid["prediction"])
    denom = np.abs(valid["actual"]).sum()
    return {
        "mae": float(error.mean()),
        "wape": float(error.sum() / denom * 100) if denom > 0 else None,
        "coverage": float(((valid["actual"] >= valid["lower"]) & (valid["actual"] <= valid["upper"])).mean()),
        "mean_interval_width": float((valid["upper"] - valid["lower"]).mean()),
        "n": int(len(valid)),
    }


def choose_model(scores: dict[str, float]) -> str:
    """Stable ties favor the simpler method in MODELS order."""
    finite = {name: value for name, value in scores.items() if np.isfinite(value)}
    if not finite:
        return "persistence"
    return min(finite, key=lambda name: (round(finite[name], 10), MODELS.index(name)))

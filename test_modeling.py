import numpy as np
import pandas as pd
import pytest

from wardcast.features import build_features, origin_rows, training_rows
from wardcast.modeling import MODELS, baseline_predictions, choose_model, conformal_radius, fit_model, metrics, prediction_intervals
from wardcast.training import _prior_residuals, _selection


def model_fixture():
    dates = pd.date_range("2022-04-01", periods=36, freq="MS")
    panel = pd.DataFrame([
        {"code": str(i), "month": date, "occupied": 80 + i * 30 + j + 5 * np.sin(j / 2), "available": 150 + i * 40}
        for i in range(8) for j, date in enumerate(dates)
    ])
    features = build_features(panel, 2)
    return training_rows(features, "2024-03-01"), origin_rows(features, "2024-03-01")


def test_baseline_fallback_and_missing_are_distinct_from_zero():
    frame = pd.DataFrame({"occupied_current": [100, 0], "occupied_seasonal_target": [np.nan, 20], "occupied_mean_3": [90, 0]})
    np.testing.assert_array_equal(baseline_predictions(frame, "persistence"), [100, 0])
    np.testing.assert_array_equal(baseline_predictions(frame, "seasonal_naive"), [100, 20])
    np.testing.assert_array_equal(baseline_predictions(frame, "trailing_mean"), [90, 0])


@pytest.mark.parametrize("name", MODELS)
def test_models_predict_finite_nonnegative_intervals(name):
    train, current = model_fixture()
    model = fit_model(name, train)
    point = model.predict(current)
    lo, hi = prediction_intervals(model, current, np.array([0.05, -0.08, 0.10, -0.12, 0.04]))
    assert np.isfinite(point).all()
    assert np.isfinite(lo).all() and np.isfinite(hi).all()
    assert (lo >= 0).all() and (lo <= point).all() and (point <= hi).all()


@pytest.mark.parametrize("name", ["ridge", "lightgbm"])
def test_explanation_adds_up_to_prediction(name):
    train, current = model_fixture()
    current = current.iloc[:2]
    model = fit_model(name, train)
    explanations = model.explanations(current)
    for (_, row), explanation, point in zip(current.iterrows(), explanations, model.predict(current)):
        reconstructed = row.occupied_current + sum(entry["contribution"] or 0 for entry in explanation)
        assert reconstructed == pytest.approx(point, abs=1e-5)


def test_finite_sample_radius_and_empty_calibration():
    assert conformal_radius(np.array([1, 2, 3, 4, 5])) == 5
    assert conformal_radius(np.array([np.nan])) is None
    _, current = model_fixture()
    with pytest.raises(ValueError, match="prior"):
        prediction_intervals(fit_model("persistence", pd.DataFrame()), current, np.array([]))


def test_metrics_hand_calculated_and_missing_actual_excluded():
    frame = pd.DataFrame({"actual": [100, 200, np.nan], "prediction": [110, 170, 1000],
                          "lower": [90, 160, 0], "upper": [120, 190, 1001]})
    result = metrics(frame)
    assert result["mae"] == 20
    assert result["wape"] == pytest.approx(100 * 40 / 300)
    assert result["coverage"] == 0.5
    assert result["mean_interval_width"] == 30
    assert result["n"] == 2


def test_selection_is_deterministic_and_favors_simple_ties():
    assert choose_model({"ridge": 10, "persistence": 10, "lightgbm": 11}) == "persistence"
    assert choose_model({"lightgbm": 9, "persistence": 10}) == "lightgbm"
    assert choose_model({}) == "persistence"


def test_calibration_excludes_unmatured_and_test_outcomes():
    records = [
        {"model": "persistence", "split": split, "target_month": pd.Timestamp(month), "actual": actual, "prediction": 100, "scale": 100}
        for split, month, actual in [("warmup", "2024-03-01", 110), ("development", "2024-04-01", 120),
                                     ("development", "2025-03-01", 130), ("test", "2025-04-01", 1000)]
    ]
    np.testing.assert_array_equal(_prior_residuals(records, "persistence", pd.Timestamp("2024-04-01"), frozen=False), [0.1, 0.2])
    np.testing.assert_array_equal(_prior_residuals(records, "persistence", pd.Timestamp("2026-03-01"), frozen=True), [0.2, 0.3])


def test_historical_selection_uses_only_matured_development_errors():
    records = [
        {"model": model, "split": "development", "target_month": pd.Timestamp(month), "actual": actual, "prediction": 100}
        for model, month, actual in [("persistence", "2024-04-01", 101), ("ridge", "2024-04-01", 105),
                                     ("persistence", "2025-03-01", 1000), ("ridge", "2025-03-01", 100)]
    ]
    assert _selection(records, pd.Timestamp("2024-04-01"))[0] == "persistence"
    assert _selection(records, pd.Timestamp("2025-03-01"))[0] == "ridge"

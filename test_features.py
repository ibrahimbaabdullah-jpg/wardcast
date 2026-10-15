import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from wardcast.features import FEATURE_COLUMNS, build_features, normalize_panel, origin_rows, training_rows


def panel_fixture(months=36):
    dates = pd.date_range("2022-04-01", periods=months, freq="MS")
    return pd.DataFrame([
        {"code": code, "month": date, "occupied": 100 + offset + i * 2,
         "available": 200 + offset + i, "quality_status": "ok"}
        for code, offset in [("A", 0), ("B", 50)] for i, date in enumerate(dates)
    ])


@pytest.mark.parametrize("horizon", [1, 2, 3])
def test_future_occupancy_and_capacity_do_not_change_origin_features(horizon):
    original = panel_fixture()
    changed = original.copy()
    cutoff = pd.Timestamp("2024-03-01")
    changed.loc[changed.month > cutoff, ["occupied", "available"]] = [90000, 100000]
    before = origin_rows(build_features(original, horizon), cutoff)
    after = origin_rows(build_features(changed, horizon), cutoff)
    assert_frame_equal(before[FEATURE_COLUMNS], after[FEATURE_COLUMNS])
    assert not before.actual.equals(after.actual)
    # Training targets after the cutoff must not affect any fitted data either.
    assert_frame_equal(training_rows(build_features(original, horizon), cutoff),
                       training_rows(build_features(changed, horizon), cutoff))


def test_calendar_lags_do_not_skip_a_missing_month():
    frame = panel_fixture()
    frame = frame.loc[~((frame.code == "A") & (frame.month == "2024-02-01"))]
    row = origin_rows(build_features(frame, 1), "2024-03-01").query("code == 'A'").iloc[0]
    assert np.isnan(row.occupied_lag_1)
    assert row.data_quality_status == "incomplete_history"
    assert row.occupied_lag_2 == 142


def test_missing_target_is_not_a_zero_and_missing_origin_not_forecast():
    frame = panel_fixture()
    frame.loc[(frame.code == "A") & (frame.month == "2024-04-01"), "occupied"] = np.nan
    features = build_features(frame, 1)
    target = origin_rows(features, "2024-03-01").query("code == 'A'").iloc[0]
    assert np.isnan(target.actual)
    assert origin_rows(features, "2024-04-01").query("code == 'A'").empty
    assert not ((training_rows(features, "2024-05-01").code == "A") &
                (training_rows(features, "2024-05-01").target_month == "2024-04-01")).any()


def test_duplicate_keys_rejected():
    frame = panel_fixture()
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_panel(pd.concat([frame, frame.iloc[[0]]]))


def test_zero_capacity_is_excluded_but_observed_zero_occupancy_is_valid():
    frame = panel_fixture()
    frame.loc[(frame.code == "A") & (frame.month == "2024-04-01"), ["occupied", "available"]] = 0
    frame.loc[(frame.code == "B") & (frame.month == "2024-04-01"), "occupied"] = 0
    features = build_features(frame, 1)
    assert origin_rows(features, "2024-04-01").code.tolist() == ["B"]
    assert origin_rows(features, "2024-04-01").iloc[0].occupied_current == 0
    assert np.isnan(origin_rows(features, "2024-03-01").query("code == 'A'").iloc[0].actual)


def test_trust_code_changes_create_separate_series():
    frame = panel_fixture().query("code == 'A'").copy()
    frame.loc[frame.month >= "2024-04-01", "code"] = "NEW"
    features = build_features(frame, 1)
    assert features.loc[features.code == "NEW", "cutoff"].min() == pd.Timestamp("2025-03-01")
    assert origin_rows(features, "2024-04-01").empty


def test_all_trusts_share_the_same_training_outcome_cutoff():
    features = build_features(panel_fixture(), 3)
    train = training_rows(features, "2024-03-01")
    assert set(train.code) == {"A", "B"}
    assert (train.target_month <= pd.Timestamp("2024-03-01")).all()
    assert train.cutoff.max() == pd.Timestamp("2023-12-01")


@pytest.mark.parametrize("horizon", [0, 4])
def test_invalid_horizon_rejected(horizon):
    with pytest.raises(ValueError, match="horizon"):
        build_features(panel_fixture(), horizon)

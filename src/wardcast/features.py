"""Calendar-aware, strictly past-only features for monthly trust forecasts."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "occupied_current", "available_current", "occupancy_current",
    "occupied_lag_1", "occupied_lag_2", "occupied_lag_3",
    "occupied_lag_6", "occupied_lag_12", "available_lag_1",
    "available_lag_3", "occupied_mean_3", "occupied_mean_6",
    "occupied_std_3", "occupied_trend_3", "capacity_trend_3",
    "occupied_seasonal_target", "target_month_sin", "target_month_cos",
]

FEATURE_LABELS = {
    "occupied_current": "Occupied beds at cutoff",
    "available_current": "Available beds at cutoff",
    "occupancy_current": "Occupancy at cutoff",
    "occupied_lag_1": "Occupied beds one month earlier",
    "occupied_lag_2": "Occupied beds two months earlier",
    "occupied_lag_3": "Occupied beds three months earlier",
    "occupied_lag_6": "Occupied beds six months earlier",
    "occupied_lag_12": "Occupied beds twelve months earlier",
    "available_lag_1": "Capacity one month earlier",
    "available_lag_3": "Capacity three months earlier",
    "occupied_mean_3": "Trailing three-month occupied mean",
    "occupied_mean_6": "Trailing six-month occupied mean",
    "occupied_std_3": "Trailing three-month variability",
    "occupied_trend_3": "Three-month occupied change",
    "capacity_trend_3": "Three-month capacity change",
    "occupied_seasonal_target": "Target month occupied beds last year",
    "target_month_sin": "Target month seasonal sine",
    "target_month_cos": "Target month seasonal cosine",
}


def normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Validate the keys; never fill missing occupancy with zero or join codes."""
    required = {"code", "month", "occupied", "available"}
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"Missing panel columns: {sorted(missing)}")
    frame = panel.copy()
    frame["month"] = pd.to_datetime(frame["month"]).dt.to_period("M").dt.to_timestamp()
    frame["code"] = frame["code"].astype(str)
    if frame.duplicated(["code", "month"]).any():
        raise ValueError("Duplicate trust-month records; resolve at ingestion before modeling")
    for col in ("occupied", "available"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
        if (frame[col].dropna() < 0).any():
            raise ValueError(f"Negative {col} observations are invalid")
        if np.isinf(frame[col]).any():
            raise ValueError(f"Infinite {col} observations are invalid")
    return frame.sort_values(["code", "month"]).reset_index(drop=True)


def build_features(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """One row per eligible origin, with outcomes kept separate from inputs.

    Reindex each code to calendar months before shifting. A missing month is a
    missing observation, not an invitation to shift the previous available row.
    A code is eligible after twelve calendar months and nine observed months.
    """
    if horizon not in (1, 2, 3):
        raise ValueError("horizon must be 1, 2, or 3")
    panel = normalize_panel(panel)
    groups = []
    for code, observed in panel.groupby("code", sort=True):
        observed = observed.set_index("month")
        dates = pd.date_range(observed.index.min(), observed.index.max(), freq="MS")
        group = observed.reindex(dates)
        available = group["available"]
        # Zero-capacity rows describe no operating bed stock. Keep them in the
        # published history but do not treat closure/non-reporting as zero demand.
        # A genuine zero occupied value with positive available capacity remains 0.
        occupied = group["occupied"].where(available > 0)
        result = pd.DataFrame(index=dates)
        result["code"] = code
        result["cutoff"] = dates
        result["target_month"] = dates + pd.DateOffset(months=horizon)
        result["horizon"] = horizon
        result["actual"] = occupied.shift(-horizon)
        result["occupied_current"] = occupied
        result["available_current"] = available
        result["occupancy_current"] = occupied / available.replace(0, np.nan)
        for lag in (1, 2, 3, 6, 12):
            result[f"occupied_lag_{lag}"] = occupied.shift(lag)
        for lag in (1, 3):
            result[f"available_lag_{lag}"] = available.shift(lag)
        result["occupied_mean_3"] = occupied.rolling(3, min_periods=2).mean()
        result["occupied_mean_6"] = occupied.rolling(6, min_periods=3).mean()
        result["occupied_std_3"] = occupied.rolling(3, min_periods=2).std()
        result["occupied_trend_3"] = occupied - occupied.shift(3)
        result["capacity_trend_3"] = available - available.shift(3)
        result["occupied_seasonal_target"] = occupied.shift(12 - horizon)
        result["target_month_sin"] = np.sin(2 * np.pi * result["target_month"].dt.month / 12)
        result["target_month_cos"] = np.cos(2 * np.pi * result["target_month"].dt.month / 12)
        quality = group.get("quality_status", pd.Series("ok", index=dates)).fillna("missing")
        incomplete = occupied.rolling(12, min_periods=1).count().lt(12)
        result["data_quality_status"] = np.where(incomplete, "incomplete_history", quality)
        eligible = (np.arange(len(dates)) >= 11) & occupied.notna() & occupied.rolling(12, min_periods=1).count().ge(9)
        groups.append(result.loc[eligible].reset_index(drop=True))
    columns = ["code", "cutoff", "target_month", "horizon", "actual", *FEATURE_COLUMNS, "data_quality_status"]
    return pd.concat(groups, ignore_index=True)[columns] if groups else pd.DataFrame(columns=columns)


def training_rows(features: pd.DataFrame, cutoff: str | pd.Timestamp) -> pd.DataFrame:
    """Exclude every outcome after the information cutoff, across all trusts."""
    cutoff = pd.Timestamp(cutoff).to_period("M").to_timestamp()
    return features.loc[(features["target_month"] <= cutoff) & features["actual"].notna()].copy()


def origin_rows(features: pd.DataFrame, cutoff: str | pd.Timestamp) -> pd.DataFrame:
    cutoff = pd.Timestamp(cutoff).to_period("M").to_timestamp()
    return features.loc[features["cutoff"] == cutoff].copy()

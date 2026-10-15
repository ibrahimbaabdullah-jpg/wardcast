"""Reproducible rolling-origin evaluation and deployment artifact creation.

Call ``train(project_root)`` after ingestion creates data/processed/panel.parquet.
No split, feature, hyperparameter, or selection decision uses test outcomes.
"""

from __future__ import annotations

import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from wardcast.features import build_features, normalize_panel, origin_rows, training_rows
from wardcast.modeling import MODELS, choose_model, fit_model, metrics, prediction_intervals

INITIAL_CUTOFF = pd.Timestamp("2024-03-01")
SELECTION_CUTOFF = pd.Timestamp("2025-03-01")
TEST_END = pd.Timestamp("2026-03-01")


def _date(value) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return _date(value)
    if isinstance(value, (float, np.floating)):
        return round(float(value), 6) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if value is pd.NA:
        return None
    return value


def _prior_residuals(records: list[dict], name: str, cutoff: pd.Timestamp, *, frozen: bool) -> np.ndarray:
    limit = SELECTION_CUTOFF if frozen else cutoff
    rows = [row for row in records if row["model"] == name and row["target_month"] <= limit
            and row["actual"] is not None and row["split"] in ("warmup", "development")]
    if frozen:
        development = [row for row in rows if row["split"] == "development"]
        rows = development or rows
    return np.array([(row["actual"] - row["prediction"]) / max(row["scale"], 1.0) for row in rows])


def _selection(records: list[dict], cutoff: pd.Timestamp) -> tuple[str, dict[str, float]]:
    scores = {}
    for name in MODELS:
        residuals = [abs(row["actual"] - row["prediction"]) for row in records
                     if row["model"] == name and row["split"] == "development"
                     and row["target_month"] <= cutoff and row["actual"] is not None]
        if residuals:
            scores[name] = float(np.mean(residuals))
    return choose_model(scores), scores


def _evaluate(records: pd.DataFrame, selected: dict[int, str]) -> dict:
    comparison = []
    for (split, horizon, name), group in records.loc[records["split"].isin(["development", "test"])].groupby(["split", "horizon", "model"], sort=True):
        comparison.append({"split": split, "horizon": int(horizon), "model": name, **metrics(group)})
    test = records.loc[(records["split"] == "test") & records.apply(lambda row: row["model"] == selected[int(row["horizon"])], axis=1)].copy()
    by_trust = [{"code": code, "horizon": int(horizon), **metrics(group)} for (code, horizon), group in test.groupby(["code", "horizon"])]
    by_horizon = [{"horizon": int(horizon), "model": selected[int(horizon)], **metrics(group)} for horizon, group in test.groupby("horizon")]
    test["period"] = np.where(pd.to_datetime(test["target_month"]).dt.month.isin([12, 1, 2]), "winter", "other")
    winter = [{"period": period, "horizon": int(horizon), **metrics(group)} for (period, horizon), group in test.groupby(["period", "horizon"])]
    selection = [{"horizon": h, "model": name, "development_mae": next(r["mae"] for r in comparison if r["split"] == "development" and r["horizon"] == h and r["model"] == name)} for h, name in selected.items()]
    return {"comparison": comparison, "by_trust": by_trust, "by_horizon": by_horizon,
            "winter": winter, "selection": selection, "primary_metric": "MAE (beds)",
            "wape_unit": "percent", "coverage_unit": "fraction", "winter_months": [12, 1, 2],
            "aggregate": metrics(test)}


def train(project_root: str | Path) -> dict:
    root = Path(project_root).resolve()
    path = root / "data/processed/panel.parquet"
    panel = normalize_panel(pd.read_parquet(path))
    if panel["month"].max() != TEST_END or panel["month"].min() != pd.Timestamp("2022-04-01"):
        raise ValueError("Expected the declared April 2022–March 2026 panel; do not silently change evaluation windows")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    source_code_digest = hashlib.sha256(b"".join((Path(__file__).parent / name).read_bytes() for name in ("features.py", "modeling.py", "training.py"))).hexdigest()
    model_version = f"wardcast-1.0-{digest[:8]}-{source_code_digest[:8]}"
    all_records, forecasts, selected, bundles = [], [], {}, {}
    for horizon in (1, 2, 3):
        print(f"Horizon {horizon}: constructing calendar-aware features", flush=True)
        features = build_features(panel, horizon)
        records = []
        selected_name = None
        # Earlier out-of-sample forecasts seed interval calibration. Their
        # outcomes are used only once mature at the current observation cutoff.
        warmup_origins = pd.date_range("2023-08-01", INITIAL_CUTOFF - pd.DateOffset(months=horizon), freq="MS")
        origins = warmup_origins.union(pd.date_range(INITIAL_CUTOFF, TEST_END, freq="MS"))
        for cutoff in origins:
            current = origin_rows(features, cutoff)
            if current.empty:
                continue
            training = training_rows(features, cutoff)
            target = cutoff + pd.DateOffset(months=horizon)
            split = "warmup" if cutoff < INITIAL_CUTOFF else (
                "development" if target <= SELECTION_CUTOFF else (
                    "test" if cutoff >= SELECTION_CUTOFF and target <= TEST_END else "replay"))
            if cutoff >= SELECTION_CUTOFF and selected_name is None:
                selected_name, _ = _selection(records, SELECTION_CUTOFF)
                selected[horizon] = selected_name
                print(f"Horizon {horizon}: froze {selected_name} using development MAE", flush=True)
            replay_name = selected_name if selected_name else _selection(records, cutoff)[0]
            candidates = {}
            for name in MODELS:
                fitted = fit_model(name, training)
                candidates[name] = fitted
                point = fitted.predict(current)
                residuals = _prior_residuals(records, name, cutoff, frozen=cutoff >= SELECTION_CUTOFF)
                if not len(residuals):
                    # Only the first warmup row lacks historical calibration.
                    # It is never exposed or included in reported metrics.
                    lower, upper = point.copy(), point.copy()
                else:
                    lower, upper = prediction_intervals(fitted, current, residuals)
                for i, (_, row) in enumerate(current.iterrows()):
                    actual = float(row["actual"]) if pd.notna(row["actual"]) else None
                    records.append({"code": row["code"], "cutoff": cutoff, "target_month": target,
                                    "horizon": horizon, "model": name, "split": split,
                                    "prediction": float(point[i]), "lower": float(lower[i]), "upper": float(upper[i]),
                                    "actual": actual, "scale": float(row["occupied_current"])})
                if cutoff >= INITIAL_CUTOFF and name == replay_name:
                    explanations = fitted.explanations(current)
                    for i, (_, row) in enumerate(current.iterrows()):
                        forecasts.append({"code": row["code"], "cutoff": cutoff, "target_month": target,
                                          "horizon": horizon, "prediction": float(point[i]), "lower": float(lower[i]), "upper": float(upper[i]),
                                          "actual": float(row["actual"]) if pd.notna(row["actual"]) else None,
                                          "baseline": float(row["occupied_current"]), "model": name,
                                          "model_version": model_version, "data_quality_status": row["data_quality_status"],
                                          "explanation": explanations[i]})
            if cutoff == TEST_END:
                bundles[horizon] = {"models": candidates, "selected_model": selected_name,
                                    "calibration_residuals": {name: _prior_residuals(records, name, cutoff, frozen=True) for name in MODELS},
                                    "training_outcome_cutoff": _date(cutoff)}
            if cutoff.month in (3, 9):
                print(f"Horizon {horizon}: evaluated origin {cutoff:%Y-%m}, {len(training):,} training examples", flush=True)
        all_records.extend(records)

    evaluation = _evaluate(pd.DataFrame(all_records), selected)
    metadata = {
        "title": "WardCast", "model_version": model_version, "cutoff": _date(TEST_END),
        "data_start": _date(panel["month"].min()), "data_end": _date(panel["month"].max()),
        "training_cutoff": _date(INITIAL_CUTOFF), "selection_cutoff": _date(SELECTION_CUTOFF),
        "development_start": "2024-04-01", "development_end": _date(SELECTION_CUTOFF),
        "test_start": "2025-04-01", "test_end": _date(TEST_END), "nominal_coverage": 0.8,
        "target": "Monthly average daily occupied adult general-and-acute beds",
        "geography": "NHS England Type 1 trusts", "trust_count": int(panel["code"].nunique()),
        "selection": evaluation["selection"], "dataset_sha256": digest, "pipeline_sha256": source_code_digest,
        "horizon_definition": "Months after the latest observation; not months after publication or forecast issue date",
        "evaluation_notes": [
            "All trusts share calendar cutoffs. Training outcomes must be observed by the origin.",
            "Zero/missing-capacity observations are excluded from model inputs and outcomes; genuine zero occupancy with positive capacity stays zero. Raw history preserves the source values.",
            "Development origins begin March 2024; frozen test origins begin March 2025. Horizons 2 and 3 omit the first 1 and 2 target months of each evaluation year.",
            "The final holdout uses monthly expanding refits with fixed hyperparameters and frozen model selection. Later test refits may use earlier test outcomes that have become observable.",
            "Before March 2025, replay model selection uses only matured development outcomes. From March 2025, the choice is frozen.",
            "Intervals have nominal 80% coverage, not a guarantee. Baseline and Ridge intervals use absolute relative residuals; final/test calibration is frozen on development residuals.",
            "LightGBM uses conditional 10th/90th quantile models, with crossing repaired and point forecasts enclosed.",
            "Publications may be delayed or revised. This is a retrospective observation-cutoff evaluation, not an as-published-vintage backtest.",
            "Monthly averages conceal daily peaks. The application is a portfolio planning demonstration, not a clinical or operational deployment.",
            "Scenarios hold predicted occupied beds fixed; changing available beds is not a causal treatment estimate.",
        ],
        "runtime": {"python": platform.python_version(), **{name: version(name) for name in ["pandas", "numpy", "scikit-learn", "lightgbm", "shap"]}},
    }
    history = panel.copy()
    history["occupancy_pct"] = history["occupied"] / history["available"].replace(0, np.nan) * 100
    trusts = []
    for code, group in panel.groupby("code", sort=True):
        latest = group.iloc[-1]
        expected = len(pd.date_range(group["month"].min(), TEST_END, freq="MS"))
        observed = int(group[["occupied", "available"]].notna().all(axis=1).sum())
        trusts.append({"code": code, "name": latest.get("name", code), "region": latest.get("region", "Unknown"),
                       "observations": observed, "last_month": latest["month"],
                       "latest_occupied": latest["occupied"], "latest_available": latest["available"],
                       "completeness": observed / expected})
    demo = _clean({"metadata": metadata, "trusts": trusts, "history": history.to_dict("records"),
                   "forecasts": sorted(forecasts, key=lambda row: (row["code"], row["cutoff"], row["horizon"])), "evaluation": evaluation})
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "demo.json").write_text(json.dumps(demo, allow_nan=False, separators=(",", ":")) + "\n")
    (artifacts / "evaluation.json").write_text(json.dumps(_clean(evaluation), indent=2, allow_nan=False) + "\n")
    joblib.dump({"metadata": metadata, "horizons": bundles}, artifacts / "models.joblib", compress=3)
    pd.DataFrame(all_records).drop(columns="scale").to_parquet(artifacts / "backtest.parquet", index=False)
    _write_docs(root, metadata, evaluation)
    print(f"Saved {len(forecasts):,} replay/future forecasts, {len(trusts)} trust summaries, and trained models", flush=True)
    for item in evaluation["by_horizon"]:
        print(f"H{item['horizon']} {item['model']}: test MAE={item['mae']:.2f} beds, WAPE={item['wape']:.2f}%, coverage={item['coverage']:.1%}", flush=True)
    return demo


def _write_docs(root: Path, metadata: dict, evaluation: dict) -> None:
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    table = ["| Split | Horizon | Model | MAE (beds) | WAPE | 80% interval coverage | Mean width (beds) | N |",
             "|---|---:|---|---:|---:|---:|---:|---:|"]
    for row in evaluation["comparison"]:
        table.append(f"| {row['split']} | {row['horizon']} | {row['model']} | {row['mae']:.2f} | {row['wape']:.2f}% | {row['coverage']:.1%} | {row['mean_interval_width']:.2f} | {row['n']} |")
    selected = "; ".join(f"h{r['horizon']}: **{r['model']}** (development MAE {r['development_mae']:.2f} beds)" for r in evaluation["selection"])
    notes = "\n".join(f"- {note}" for note in metadata["evaluation_notes"])
    benchmark = f"""# Benchmark report

Generated by `wardcast train` from dataset `{metadata['dataset_sha256']}`.
Model version: `{metadata['model_version']}`. These are measured results, not illustrative scores.

## Protocol

The data cover April 2022–March 2026. Initial training ends March 2024. Development target months end March 2025; the final test target months end March 2026. Development origins begin March 2024 and test origins begin March 2025, so horizons 1/2/3 have up to 12/11/10 target months respectively. This prevents model selection using outcomes later than an evaluation origin.

Each horizon uses a separate pooled model across trusts. Refits expand monthly, only with outcomes at or before the origin. No future capacity enters features. Feature preprocessing is refit within each training fold. Trust codes remain separate, and missing calendar months remain missing. A trust needs twelve calendar months and nine observed occupied months, plus observed current occupancy, to obtain a forecast.

The fixed candidate set is persistence, seasonal naive (the target calendar month last year), trailing-three-month mean, Ridge on occupied-bed changes (alpha 100), and shallow LightGBM on changes (100 trees, 7 leaves, depth 3, learning rate 0.04, L1 objective, seed 42, two CPU threads). Hyperparameters are fixed before evaluation. Model selection minimizes development bed-count MAE, with deterministic ties favoring the simpler method. Larger trusts contribute larger absolute errors; WAPE and trust-level breakdowns help contextualize this.

Selected methods: {selected}.

## All candidates

{chr(10).join(table)}

WAPE is `100 × sum(abs(error)) / sum(abs(actual))`; it is not an unweighted average of trust percentages. Coverage is a fraction in API artifacts and a percentage here. Width is the mean upper-minus-lower interval in beds. The per-trust, horizon, and winter (December–February) tables are in `artifacts/evaluation.json`; individual predictions are in `artifacts/backtest.parquet`.

## Interpretation and limitations

{notes}

These outcomes measure predictive association, not causality. The final candidate comparison is transparency reporting; it does not change the development-selected deployment model. No significance claim is made from correlated trust/month observations. A baseline winning is a valid finding: complexity must earn its place.
"""
    (docs / "benchmark.md").write_text(benchmark)
    card = f"""# WardCast model card

**Version:** `{metadata['model_version']}`  
**Task:** Forecast trust-level monthly average daily occupied adult general-and-acute beds, 1–3 months after the latest observation.  
**Intended users:** Portfolio reviewers and healthcare operations analysts exploring a retrospective demonstration.  
**Not validated for:** Clinical decisions, daily surge detection, staffing allocation, bed closures, live operational decision-making, or causal policy effects.

## Data and provenance

Public NHS England monthly urgent-and-emergency-care situation-report bed statistics, April 2022–March 2026. Source files, URLs, download hashes, parsing details, and attribution are documented in the data provenance deliverables. No patient-level or private information is used. Trust codes are not silently stitched across mergers. Missing values are kept as missing; source updates and code changes may create series discontinuities.

Input panel SHA-256: `{metadata['dataset_sha256']}`. Pipeline source SHA-256: `{metadata['pipeline_sha256']}`.

## Model and features

Separate pooled models for each horizon. Candidate models are persistence, calendar-seasonal naive, trailing mean, Ridge, and LightGBM. Inputs are current occupied/available beds, historical lags and rolling summaries, historical occupancy, and the known target calendar month. The outcome is occupied beds, never the future observed capacity. Ridge and LightGBM predict a change from current occupancy; nonnegative output clipping is applied.

Selection: {selected}. Final model objects for all candidates are saved in `artifacts/models.joblib`; the selected methods drive the application. Load pickle/joblib artifacts only from trusted sources.

## Explanations

Baseline explanations report the exact input used. Ridge explanations report additive effects of standardized, median-imputed features on predicted change, with the intercept. Tree explanations use SHAP on the change model. The five largest effects, remaining-feature sum, expected change, and any nonnegative adjustment preserve the additive prediction. These explanations describe model behavior, not causal effects. Missing feature values may be imputed for Ridge and routed natively by LightGBM.

## Uncertainty

Nominal coverage is 80%. Baseline/Ridge intervals use a finite-sample rank of absolute residuals divided by origin occupied beds, scaled back to the current trust; zero occupancy uses a denominator floor of one bed. Development calibration uses only matured earlier out-of-sample residuals, seeded with pre-development warmup forecasts. Test/latest calibration is frozen on development residuals. Tree intervals use separate 0.10 and 0.90 quantile models; crossings are ordered and the point forecast enclosed. These are empirical prediction intervals, not certified conformal guarantees for dependent time series. Read measured coverage and width alongside point error in the benchmark.

## Evaluation and limitations

{notes}

Completeness is the share of expected monthly rows since the code first appears with both occupied and available beds observed; it is not proof of source accuracy. New/short series may have history but no model forecasts. Cohort membership, pandemic recovery, reporting changes, mergers, and changing service configuration can affect generalization. Region is descriptive, not a proxy for a protected characteristic. No individual-level fairness or health-outcome inference is supported.

## Reproduction and maintenance

Use the repository ingestion and training commands. CPU only; seed 42; LightGBM uses two threads. Exact runtime package versions are recorded in `artifacts/demo.json` metadata. Updates beyond March 2026 require a deliberate revision of the declared evaluation windows and a fresh chronological evaluation. Monitor missingness, schema changes, drift, MAE, interval coverage, and code changes before any live deployment.
"""
    (docs / "model-card.md").write_text(card)

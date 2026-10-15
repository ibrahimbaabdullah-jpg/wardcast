# WardCast model card

**Version:** `wardcast-1.0-bbbf9cbf-9864260e`  
**Task:** Forecast trust-level monthly average daily occupied adult general-and-acute beds, 1–3 months after the latest observation.  
**Intended users:** Portfolio reviewers and healthcare operations analysts exploring a retrospective demonstration.  
**Not validated for:** Clinical decisions, daily surge detection, staffing allocation, bed closures, live operational decision-making, or causal policy effects.

## Data and provenance

Public NHS England monthly urgent-and-emergency-care situation-report bed statistics, April 2022–March 2026. Source files, URLs, download hashes, parsing details, and attribution are documented in the data provenance deliverables. No patient-level or private information is used. Trust codes are not silently stitched across mergers. Missing values are kept as missing; source updates and code changes may create series discontinuities.

Input panel SHA-256: `bbbf9cbf46c9b253b808000f7a482f8275827fcbd10a76d70cafcdf37110994d`. Pipeline source SHA-256: `9864260eff5e37996dd5b68c1b910ec8f226848f8e847020f87b7a49fad25dd5`.

## Model and features

Separate pooled models for each horizon. Candidate models are persistence, calendar-seasonal naive, trailing mean, Ridge, and LightGBM. Inputs are current occupied/available beds, historical lags and rolling summaries, historical occupancy, and the known target calendar month. The outcome is occupied beds, never the future observed capacity. Ridge and LightGBM predict a change from current occupancy; nonnegative output clipping is applied.

Selection: h1: **lightgbm** (development MAE 11.77 beds); h2: **lightgbm** (development MAE 15.47 beds); h3: **lightgbm** (development MAE 17.99 beds). Final model objects for all candidates are saved in `artifacts/models.joblib`; the selected methods drive the application. Load pickle/joblib artifacts only from trusted sources.

## Explanations

Baseline explanations report the exact input used. Ridge explanations report additive effects of standardized, median-imputed features on predicted change, with the intercept. Tree explanations use SHAP on the change model. The five largest effects, remaining-feature sum, expected change, and any nonnegative adjustment preserve the additive prediction. These explanations describe model behavior, not causal effects. Missing feature values may be imputed for Ridge and routed natively by LightGBM.

## Uncertainty

Nominal coverage is 80%. Baseline/Ridge intervals use a finite-sample rank of absolute residuals divided by origin occupied beds, scaled back to the current trust; zero occupancy uses a denominator floor of one bed. Development calibration uses only matured earlier out-of-sample residuals, seeded with pre-development warmup forecasts. Test/latest calibration is frozen on development residuals. Tree intervals use separate 0.10 and 0.90 quantile models; crossings are ordered and the point forecast enclosed. These are empirical prediction intervals, not certified conformal guarantees for dependent time series. Read measured coverage and width alongside point error in the benchmark.

## Evaluation and limitations

- All trusts share calendar cutoffs. Training outcomes must be observed by the origin.
- Zero/missing-capacity observations are excluded from model inputs and outcomes; genuine zero occupancy with positive capacity stays zero. Raw history preserves the source values.
- Development origins begin March 2024; frozen test origins begin March 2025. Horizons 2 and 3 omit the first 1 and 2 target months of each evaluation year.
- The final holdout uses monthly expanding refits with fixed hyperparameters and frozen model selection. Later test refits may use earlier test outcomes that have become observable.
- Before March 2025, replay model selection uses only matured development outcomes. From March 2025, the choice is frozen.
- Intervals have nominal 80% coverage, not a guarantee. Baseline and Ridge intervals use absolute relative residuals; final/test calibration is frozen on development residuals.
- LightGBM uses conditional 10th/90th quantile models, with crossing repaired and point forecasts enclosed.
- Publications may be delayed or revised. This is a retrospective observation-cutoff evaluation, not an as-published-vintage backtest.
- Monthly averages conceal daily peaks. The application is a portfolio planning demonstration, not a clinical or operational deployment.
- Scenarios hold predicted occupied beds fixed; changing available beds is not a causal treatment estimate.

Completeness is the share of expected monthly rows since the code first appears with both occupied and available beds observed; it is not proof of source accuracy. New/short series may have history but no model forecasts. Cohort membership, pandemic recovery, reporting changes, mergers, and changing service configuration can affect generalization. Region is descriptive, not a proxy for a protected characteristic. No individual-level fairness or health-outcome inference is supported.

## Reproduction and maintenance

Use the repository ingestion and training commands. CPU only; seed 42; LightGBM uses two threads. Exact runtime package versions are recorded in `artifacts/demo.json` metadata. Updates beyond March 2026 require a deliberate revision of the declared evaluation windows and a fresh chronological evaluation. Monitor missingness, schema changes, drift, MAE, interval coverage, and code changes before any live deployment.

# Release verification

This report describes checks actually run for the bundled WardCast release.
It is not a claim that a GitHub Actions run or Docker deployment has already occurred.

| Check | Result |
|---|---|
| Python tests | 63 passed |
| Ruff source and test checks | Passed |
| Python dependency consistency (`pip check`) | Passed |
| TypeScript and Vite production build | Passed |
| Playwright Chromium workflows against production FastAPI + built frontend | 4 passed |
| Responsive layout | 390 × 844 browser test; no horizontal page overflow |
| Source download and preparation | All 48 pinned official files verified and parsed |
| Full ingestion/training reproduction | Completed twice; identical `demo.json` bytes on this machine |
| Independent metric audit | All 30 aggregate development/test candidate rows reproduced from saved predictions |
| Forecast artifact audit | Finite ordered intervals, forecast/SHAP reconstruction, final serialized-model agreement |
| Docker image execution | Not run locally: Docker is unavailable; CI smoke test supplied |
| Hosted GitHub workflow | Supplied, not yet run on a published repository |

The browser workflows cover capacity edits and reset, fixed occupied-bed predictions,
baseline comparison, historical replay and outcomes, a second trust, development/test
evidence, the 48-file source manifest, zero-capacity history without invented
forecasts, invalid capacity, and mobile layout. Desktop screenshots are included
in `docs/screenshots`.

The model review checked calendar-aligned lags, shared trust cutoffs, training
outcomes no later than each origin, model selection using development data only,
and interval calibration without future outcomes. Retrospective source revisions
still limit what can be inferred about historical real-time performance.

The local Python run emitted a dependency deprecation warning and Ridge/BLAS
floating-point warnings; assertions and artifact checks confirmed finite outputs.
They are not hidden or converted into evidence of improved model performance.

Reproduction is deterministic on the tested local environment. Other platforms
or numeric libraries can produce small floating-point differences. See the
pinned dependency files and model-card runtime metadata.

Bundled forecast SHA-256: `fed5f92e5cf580d85c60dea8c2d3fda8e225994208a5f76338ee0b9e79559e3b`.

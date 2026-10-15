# WardCast API

The FastAPI service reads `artifacts/demo.json` once after its first successful request. Restart it after rebuilding the bundle. Set `WARDCAST_BUNDLE` to use another bundle. Missing or invalid artifacts return `503` with a rebuild instruction; importing the application does not require artifacts to exist. Interactive OpenAPI documentation is available at `/docs` and the schema at `/openapi.json`.

| Method and path | Result |
| --- | --- |
| `GET /api/health` | Readiness, model version, trust count, and latest observation cutoff |
| `GET /api/meta` | Dataset dates, evaluation periods, interval target, model selection, and caveats |
| `GET /api/trusts` | `{trusts: [...]}`, alphabetically sorted by name |
| `GET /api/history/{code}` | Trust metadata and observations, oldest first; missing values remain `null` |
| `GET /api/cutoffs/{code}` | `{cutoffs: [...]}`, most recent first |
| `GET /api/forecasts/{code}?cutoff=YYYY-MM-01` | Forecasts for the specified observation cutoff, sorted by horizon |
| `POST /api/scenarios` | Capacity calculations with the original forecasts held fixed |
| `GET /api/evaluation` | Development/test comparisons, selected models, trust/horizon/winter metrics |
| `GET /api/sources` | Download provenance from `data/source_manifest.json` |

Omitting `cutoff` selects the latest available forecast cutoff for that trust. A cutoff is the last observation month used by the model, not a real-world publication or issue date. All month values use the first day of the month. Unknown trusts and unavailable cutoffs return `404`; malformed months and invalid request bodies return `422`.

Forecast responses contain `trust`, `cutoff`, `model_version`, `data_quality_status`, and `forecasts`. Each forecast has `code`, `cutoff`, `target_month`, `horizon`, `prediction`, `lower`, `upper`, `actual`, `baseline`, `model`, `model_version`, `data_quality_status`, and `explanation`. `baseline` is the persistence prediction. `actual` is `null` when the target has not been observed. Explanations contain `feature`, `label`, `value`, and nullable `contribution`; contribution units depend on the model and should be shown only when present. Predictions and intervals are monthly average daily occupied adult beds.

## Capacity scenarios

```json
{
  "trust_code": "R0A",
  "cutoff": "2026-03-01",
  "capacity": 1200
}
```

The optional cutoff uses the same semantics as the forecast endpoint. Capacity must be a positive, finite JSON number. Extra request fields are rejected. No scenario is persisted and no model is retrained.

Each response forecast adds:

- `occupancy_pct = 100 × prediction / capacity`
- `margin = capacity − prediction`
- `lower_margin = capacity − upper`
- `upper_margin = capacity − lower`

Negative margins represent predicted occupied beds above the assumed average available capacity. Occupancy percentages can exceed 100%. The interval endpoints reverse when converting predicted occupied beds to capacity margin. Changing capacity does not alter occupied-bed predictions or prediction intervals. These are arithmetic planning scenarios, not causal estimates of the effect of opening beds.

## Serving and development

The service serves `frontend/dist` when that directory contains `index.html` at application creation. Set `WARDCAST_FRONTEND_DIST` to override the directory. Frontend routes fall back to the index, while missing assets and unknown `/api/` paths remain `404`. Development CORS allows only `http://localhost:5173` and `http://127.0.0.1:5173`; production uses the same origin. There are no data mutation endpoints, credentials, or external model-service calls.

Run `wardcast serve --host 127.0.0.1 --port 8000` from the repository root after building the frontend, or use `make demo`. The bundled forecasts serve without source downloads or retraining. The CLI also accepts `wardcast --root /path/to/wardcast serve` when launched from another directory.

## Docker and continuous integration

`docker compose up --build` compiles the frontend with Node 22 and pnpm 11.25.0, installs the locked Python 3.12 environment, and serves the application at `http://127.0.0.1:8000`. The runtime includes the public-data panel, source manifest, trained models, and demo forecasts. Raw publications, development environments, and local secrets are excluded. The application runs as a non-root user; Compose exposes its port on loopback and uses a read-only filesystem. The health check verifies that the forecast bundle can be loaded, not merely that a process is listening.

GitHub Actions runs Python checks, compiles the frontend, and exercises the browser workflow against the bundled API. It then builds the image and checks its health, source endpoint, and static frontend. CI does not download NHS publications or retrain models. Locally, run `make browsers` once, start `make serve` in one terminal, and run `make e2e` in another; Playwright starts the Vite development server.

`make test` runs Python checks and, on macOS, makes scikit-learn's bundled OpenMP runtime available before importing LightGBM. It does not modify system libraries. Installing `libomp` with Homebrew is an alternative when a Python environment does not contain that bundled runtime. The Docker image provides `libgomp1` for Linux.

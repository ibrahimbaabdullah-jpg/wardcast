"""Read-only forecast API and deterministic capacity scenario arithmetic."""

import json
import logging
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from wardcast.schemas import (
    CutoffsResponse,
    DemoBundle,
    Evaluation,
    ForecastResponse,
    HistoryResponse,
    Month,
    ScenarioForecast,
    ScenarioRequest,
    ScenarioResponse,
    Trust,
    TrustList,
)


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def _parse_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number is outside the finite floating-point range")
    return number


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_reject_nonfinite, parse_float=_parse_finite_float)


def create_app(
    bundle_path: str | Path | None = None,
    *,
    static_dir: str | Path | None = None,
) -> FastAPI:
    """Create an isolated app; defer reading artifacts until the first request.

    A successful read is cached for this application instance. Restart the server
    after retraining. Importing this module does not require a trained bundle.
    """

    project_root = Path(os.environ.get("WARDCAST_ROOT", PROJECT_ROOT)).resolve()
    path = Path(
        bundle_path or os.environ.get("WARDCAST_BUNDLE", project_root / "artifacts/demo.json")
    ).resolve()
    frontend = Path(
        static_dir or os.environ.get("WARDCAST_FRONTEND_DIST", project_root / "frontend/dist")
    ).resolve()
    app = FastAPI(
        title="WardCast API",
        version="1.0.0",
        description=(
            "Monthly NHS trust capacity planning from retrospective public data. "
            "Horizons are months after the observation cutoff, not issue dates."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic includes the original bad input in validation errors. Replace
        # non-finite inputs there as well, so invalid JSON numbers never become
        # a response-serialization failure instead of the intended 422.
        errors = jsonable_encoder(
            exc.errors(),
            custom_encoder={float: lambda value: value if math.isfinite(value) else str(value)},
        )
        return JSONResponse(status_code=422, content={"detail": errors})

    @lru_cache(maxsize=1)
    def get_bundle() -> DemoBundle:
        try:
            bundle = DemoBundle.model_validate(_load_json(path))
            trust_codes = [trust.code for trust in bundle.trusts]
            if len(trust_codes) != len(set(trust_codes)):
                raise ValueError("Duplicate trust codes in the forecast bundle")
            known = set(trust_codes)
            forecast_keys = [(row.code, row.cutoff, row.horizon) for row in bundle.forecasts]
            history_keys = [(row.code, row.month) for row in bundle.history]
            if len(forecast_keys) != len(set(forecast_keys)):
                raise ValueError("Duplicate forecast records in the forecast bundle")
            if len(history_keys) != len(set(history_keys)):
                raise ValueError("Duplicate history records in the forecast bundle")
            if any(row.code not in known for row in (*bundle.history, *bundle.forecasts)):
                raise ValueError("Unknown trust code in the forecast bundle")
            return bundle
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Forecast bundle is unavailable. Run the WardCast data and "
                    "training commands in the README, then restart the server."
                ),
            ) from exc
        except (OSError, ValueError, ValidationError) as exc:
            logger.error("Could not validate WardCast bundle %s: %s", path, exc)
            raise HTTPException(
                status_code=503,
                detail="Forecast bundle is invalid or unreadable. Rebuild it and restart the server.",
            ) from exc

    def find_trust(code: str) -> Trust:
        for trust in get_bundle().trusts:
            if trust.code == code:
                return trust
        raise HTTPException(status_code=404, detail=f"Unknown trust code: {code}")

    def get_forecast_response(code: str, cutoff: str | None) -> ForecastResponse:
        trust = find_trust(code)
        all_rows = [row for row in get_bundle().forecasts if row.code == code]
        if not all_rows:
            raise HTTPException(status_code=404, detail="No forecasts are available for this trust")
        selected_cutoff = cutoff or max(row.cutoff for row in all_rows)
        rows = sorted(
            (row for row in all_rows if row.cutoff == selected_cutoff),
            key=lambda row: row.horizon,
        )
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No forecasts for observation cutoff {selected_cutoff}; see /api/cutoffs/{code}",
            )
        statuses = sorted({row.data_quality_status for row in rows})
        versions = sorted({row.model_version for row in rows})
        return ForecastResponse(
            trust=trust,
            cutoff=selected_cutoff,
            model_version=", ".join(versions),
            data_quality_status=", ".join(statuses),
            forecasts=rows,
        )

    @app.get("/api/health", tags=["service"])
    def health() -> dict[str, Any]:
        bundle = get_bundle()
        return {
            "status": "ok",
            "model_version": bundle.metadata.get("model_version"),
            "trusts": len(bundle.trusts),
            "cutoff": bundle.metadata.get("cutoff"),
        }

    @app.get("/api/meta", tags=["service"])
    def metadata() -> dict[str, Any]:
        return get_bundle().metadata

    @app.get("/api/trusts", response_model=TrustList, tags=["data"])
    def trusts() -> TrustList:
        return TrustList(trusts=sorted(get_bundle().trusts, key=lambda trust: trust.name))

    @app.get("/api/history/{code}", response_model=HistoryResponse, tags=["data"])
    def history(code: str) -> HistoryResponse:
        trust = find_trust(code)
        observations = sorted(
            (row for row in get_bundle().history if row.code == code),
            key=lambda row: row.month,
        )
        return HistoryResponse(trust=trust, observations=observations)

    @app.get("/api/cutoffs/{code}", response_model=CutoffsResponse, tags=["forecasts"])
    def cutoffs(code: str) -> CutoffsResponse:
        find_trust(code)
        return CutoffsResponse(
            cutoffs=sorted(
                {row.cutoff for row in get_bundle().forecasts if row.code == code},
                reverse=True,
            )
        )

    @app.get("/api/forecasts/{code}", response_model=ForecastResponse, tags=["forecasts"])
    def forecasts(code: str, cutoff: Annotated[Month | None, Query()] = None) -> ForecastResponse:
        return get_forecast_response(code, cutoff)

    @app.post("/api/scenarios", response_model=ScenarioResponse, tags=["forecasts"])
    def scenarios(request: ScenarioRequest) -> ScenarioResponse:
        response = get_forecast_response(request.trust_code, request.cutoff)
        rows: list[ScenarioForecast] = []
        for forecast in response.forecasts:
            occupancy_pct = forecast.prediction / request.capacity * 100
            if not math.isfinite(occupancy_pct):
                raise HTTPException(
                    status_code=422, detail="Capacity is too small to calculate finite occupancy"
                )
            rows.append(
                ScenarioForecast(
                    **forecast.model_dump(),
                    occupancy_pct=occupancy_pct,
                    margin=request.capacity - forecast.prediction,
                    lower_margin=request.capacity - forecast.upper,
                    upper_margin=request.capacity - forecast.lower,
                )
            )
        return ScenarioResponse(
            **response.model_dump(exclude={"forecasts"}),
            capacity=request.capacity,
            forecasts=rows,
        )

    @app.get("/api/evaluation", response_model=Evaluation, tags=["evidence"])
    def evaluation() -> Evaluation:
        return get_bundle().evaluation

    @app.get("/api/sources", tags=["evidence"])
    def sources() -> Any:
        manifest = project_root / "data/source_manifest.json"
        try:
            return _load_json(manifest)
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=503, detail="Source manifest is unavailable or unreadable"
            ) from exc

    if (frontend / "index.html").is_file():

        @app.get("/{file_path:path}", include_in_schema=False)
        def frontend_file(file_path: str) -> FileResponse:
            if file_path == "api" or file_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Unknown API endpoint")
            candidate = (frontend / file_path).resolve()
            if candidate != frontend and frontend not in candidate.parents:
                raise HTTPException(status_code=404, detail="File not found")
            if candidate.is_file():
                return FileResponse(candidate)
            if Path(file_path).suffix:
                raise HTTPException(status_code=404, detail="File not found")
            return FileResponse(frontend / "index.html")

    return app


app = create_app()

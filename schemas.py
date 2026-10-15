"""Public API contracts for the immutable WardCast demonstration bundle."""

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator


def _valid_month(value: str) -> str:
    date.fromisoformat(value)
    return value


Month = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])-01$"),
    AfterValidator(_valid_month),
]
FiniteNumber = Annotated[float, Field(allow_inf_nan=False)]
NonnegativeNumber = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Horizon = Annotated[int, Field(ge=1, le=3)]


class PublicModel(BaseModel):
    """Allow supplementary provenance while validating the documented contract."""

    model_config = ConfigDict(extra="allow", frozen=True, allow_inf_nan=False)


class Trust(PublicModel):
    code: str
    name: str
    region: str
    observations: Annotated[int, Field(ge=0)]
    last_month: Month
    latest_occupied: NonnegativeNumber | None
    latest_available: NonnegativeNumber | None
    completeness: NonnegativeNumber


class Observation(PublicModel):
    code: str
    name: str
    region: str
    month: Month
    occupied: NonnegativeNumber | None
    available: NonnegativeNumber | None
    quality_status: str
    source_id: str
    occupancy_pct: NonnegativeNumber | None


class Explanation(PublicModel):
    feature: str
    label: str
    value: FiniteNumber | str | None
    contribution: FiniteNumber | None = None


class Forecast(PublicModel):
    code: str
    cutoff: Month
    target_month: Month
    horizon: Horizon
    prediction: NonnegativeNumber
    lower: NonnegativeNumber
    upper: NonnegativeNumber
    actual: NonnegativeNumber | None
    baseline: NonnegativeNumber
    model: str
    model_version: str
    data_quality_status: str
    explanation: list[Explanation] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_interval(self) -> "Forecast":
        if not self.lower <= self.prediction <= self.upper:
            raise ValueError("Forecast interval must contain the point prediction")
        return self


class ScenarioForecast(Forecast):
    occupancy_pct: NonnegativeNumber
    margin: FiniteNumber
    lower_margin: FiniteNumber
    upper_margin: FiniteNumber


class MetricGroup(PublicModel):
    horizon: Horizon
    mae: NonnegativeNumber | None = None
    wape: NonnegativeNumber | None = None
    coverage: NonnegativeNumber | None = None
    mean_interval_width: NonnegativeNumber | None = None
    n: Annotated[int, Field(ge=0)]


class Comparison(MetricGroup):
    split: Literal["development", "test"]
    model: str


class TrustMetrics(MetricGroup):
    code: str


class WinterMetrics(MetricGroup):
    period: Literal["winter", "other"]


class Selection(PublicModel):
    horizon: Horizon
    model: str
    development_mae: NonnegativeNumber


class Evaluation(PublicModel):
    primary_metric: str
    comparison: list[Comparison]
    by_trust: list[TrustMetrics]
    by_horizon: list[MetricGroup]
    winter: list[WinterMetrics]
    selection: list[Selection]


class DemoBundle(PublicModel):
    metadata: dict[str, Any]
    trusts: list[Trust]
    history: list[Observation]
    forecasts: list[Forecast]
    evaluation: Evaluation


class TrustList(PublicModel):
    trusts: list[Trust]


class HistoryResponse(PublicModel):
    trust: Trust
    observations: list[Observation]


class CutoffsResponse(PublicModel):
    cutoffs: list[Month]


class ForecastResponse(PublicModel):
    trust: Trust
    cutoff: Month
    model_version: str
    data_quality_status: str
    forecasts: list[Forecast]


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust_code: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    cutoff: Month | None = None
    capacity: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]


class ScenarioResponse(ForecastResponse):
    capacity: FiniteNumber
    forecasts: list[ScenarioForecast]

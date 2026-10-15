export interface Trust {
  code: string;
  name: string;
  region?: string;
  observations: number;
  last_month: string;
  latest_occupied: number | null;
  latest_available: number | null;
  completeness: number;
}

export interface Observation {
  code: string;
  month: string;
  occupied: number | null;
  available: number | null;
  occupancy_pct: number | null;
  quality_status: string;
  source_id: string;
}

export interface Explanation {
  feature: string;
  label: string;
  value: number | string | null;
  contribution: number | null;
}

export interface Forecast {
  code: string;
  cutoff: string;
  target_month: string;
  horizon: number;
  prediction: number;
  lower: number;
  upper: number;
  actual: number | null;
  baseline: number;
  model: string;
  model_version: string;
  data_quality_status: string;
  explanation: Explanation[];
}

export interface ForecastResponse {
  trust: Trust;
  cutoff: string;
  model_version: string;
  data_quality_status: string;
  forecasts: Forecast[];
}

export interface ScenarioRow extends Forecast {
  occupancy_pct: number;
  margin: number;
  lower_margin: number;
  upper_margin: number;
}

export interface ScenarioResponse {
  capacity: number;
  forecasts: ScenarioRow[];
}

export interface Metric {
  split?: string;
  model?: string;
  code?: string;
  horizon: number;
  mae: number;
  wape: number | null;
  coverage?: number | null;
  mean_interval_width?: number | null;
  n: number;
  period?: string;
}

export interface Evaluation {
  comparison: Metric[];
  by_trust: Metric[];
  by_horizon: Metric[];
  winter: Metric[];
  selection: { horizon: number; model: string; development_mae: number }[];
  primary_metric: string;
}

export interface Source {
  id?: string;
  source_id?: string;
  month?: string;
  period?: string;
  url?: string;
  source_url?: string;
  filename?: string;
  sha256?: string;
  [key: string]: unknown;
}

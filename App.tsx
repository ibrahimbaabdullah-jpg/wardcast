import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { modelName, month, number, percent, request } from './api';
import type {
  Evaluation,
  Forecast,
  ForecastResponse,
  Metric,
  Observation,
  ScenarioResponse,
  Source,
  Trust,
} from './types';

type View = 'overview' | 'evidence' | 'methods';
type IconName =
  | 'chart'
  | 'evidence'
  | 'database'
  | 'arrow'
  | 'chevron'
  | 'refresh'
  | 'check'
  | 'info'
  | 'layers'
  | 'external';

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    chart: (
      <>
        <path d="M4 4v16h16" />
        <path d="m7 14 4-5 4 3 5-7" />
      </>
    ),
    evidence: (
      <>
        <path d="M8 3H5v18h14V3h-3" />
        <path d="M9 2h6v4H9zM8 11h8M8 15h5" />
      </>
    ),
    database: (
      <>
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0" />
      </>
    ),
    arrow: (
      <>
        <path d="M5 12h14m-6-6 6 6-6 6" />
      </>
    ),
    chevron: <path d="m8 5 7 7-7 7" />,
    refresh: (
      <>
        <path d="M20 7v5h-5M4 17v-5h5" />
        <path d="M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v6M12 7h.01" />
      </>
    ),
    layers: (
      <>
        <path d="m12 3 10 5-10 5L2 8zM2 12l10 5 10-5M2 16l10 5 10-5" />
      </>
    ),
    external: (
      <>
        <path d="M14 3h7v7M21 3l-12 12M11 3H3v18h18v-8" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function MetricCard({
  label,
  value,
  unit,
  detail,
  accent = false,
  children,
}: {
  label: string;
  value: string;
  unit?: string;
  detail: string;
  accent?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className={`metric-card${accent ? ' accent' : ''}`}>
      <div className="eyebrow">{label}</div>
      <div className="metric-value">
        {value}
        <span>{unit}</span>
      </div>
      <div className="metric-detail">
        {children}
        {detail}
      </div>
    </div>
  );
}

function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="error-notice" role="alert">
      <Icon name="info" />
      <div>
        <strong>We couldn’t load this view</strong>
        <p>{message}</p>
        {retry && (
          <button className="text-button" onClick={retry}>
            Try again <Icon name="refresh" size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

function ForecastChart({
  observations,
  forecasts,
  cutoff,
  showBaseline,
}: {
  observations: Observation[];
  forecasts: Forecast[];
  cutoff: string;
  showBaseline: boolean;
}) {
  const data = useMemo(() => {
    const history = observations.filter((item) => item.month <= cutoff).slice(-12);
    const latest = history.at(-1);
    return [
      ...history.map((item) => ({
        month: item.month,
        observed: item.occupied,
        available: item.available,
        forecast: item.month === latest?.month ? item.occupied : null,
        range: null as number[] | null,
        baseline: item.month === latest?.month ? item.occupied : null,
        actual: null as number | null,
      })),
      ...forecasts.map((item) => ({
        month: item.target_month,
        observed: null,
        available: null,
        forecast: item.prediction,
        range: [item.lower, item.upper],
        baseline: item.baseline,
        actual: item.actual,
      })),
    ];
  }, [observations, forecasts, cutoff]);
  return (
    <div
      className="forecast-chart"
      role="img"
      aria-label={`Observed occupied and available beds through ${month(cutoff)}, with three monthly forecasts and nominal 80 percent prediction intervals. Exact forecasts are available in the table below.`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data}
          margin={{ top: 14, right: 14, left: 3, bottom: 8 }}
          accessibilityLayer
        >
          <defs>
            <linearGradient id="uncertaintyFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1a8b77" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#1a8b77" stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#e7eeeb" vertical={false} strokeDasharray="3 4" />
          <XAxis
            dataKey="month"
            tickFormatter={(value: string) => month(value).replace(' 20', ' ’')}
            axisLine={false}
            tickLine={false}
            minTickGap={24}
            tick={{ fill: '#7c898b', fontSize: 11 }}
            dy={10}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            width={48}
            domain={['auto', 'auto']}
            tick={{ fill: '#7c898b', fontSize: 11 }}
            tickFormatter={(value: number) => number(value)}
          />
          <Tooltip
            labelFormatter={(label) => month(String(label), 'long')}
            formatter={(value, name) => [
              Array.isArray(value)
                ? value.map((v) => number(Number(v))).join(' – ')
                : `${number(Number(value), 1)} beds`,
              name,
            ]}
            contentStyle={{
              border: '1px solid #dae4df',
              borderRadius: 10,
              boxShadow: '0 6px 25px #142c3214',
              fontSize: 12,
            }}
          />
          <Area
            type="linear"
            dataKey="range"
            name="80% prediction interval"
            stroke="none"
            fill="url(#uncertaintyFill)"
            isAnimationActive={false}
          />
          <Line
            type="linear"
            dataKey="available"
            name="Available beds"
            stroke="#acb8be"
            strokeDasharray="4 4"
            strokeWidth={1.7}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="linear"
            dataKey="observed"
            name="Occupied beds"
            stroke="#193d4b"
            strokeWidth={2.6}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="linear"
            dataKey="forecast"
            name="Forecast"
            stroke="#12806a"
            strokeWidth={2.6}
            dot={{ r: 4, fill: '#12806a', stroke: '#fff', strokeWidth: 2 }}
            isAnimationActive={false}
          />
          {showBaseline && (
            <Line
              type="linear"
              dataKey="baseline"
              name="Last observed baseline"
              stroke="#d59848"
              strokeDasharray="4 3"
              strokeWidth={1.6}
              dot={false}
              isAnimationActive={false}
            />
          )}
          <Line
            type="linear"
            dataKey="actual"
            name="Subsequently observed"
            stroke="#617798"
            strokeWidth={1.5}
            strokeDasharray="2 3"
            dot={{ r: 3, stroke: '#617798', fill: '#fff' }}
            isAnimationActive={false}
          />
          <ReferenceLine
            x={cutoff}
            stroke="#b4c5be"
            strokeDasharray="4 4"
            label={{
              value: 'Forecast →',
              position: 'insideTopRight',
              fill: '#6f8580',
              fontSize: 10,
              offset: 10,
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function Overview({
  trust,
  observations,
  response,
  cutoff,
}: {
  trust: Trust;
  observations: Observation[];
  response: ForecastResponse;
  cutoff: string;
}) {
  const latest = [...observations].reverse().find((row) => row.month <= cutoff);
  const baseCapacity =
    [...observations].reverse().find((row) => row.month <= cutoff && row.available != null)
      ?.available ?? null;
  const [capacity, setCapacity] = useState(baseCapacity ? Math.round(baseCapacity) : 0);
  const [scenario, setScenario] = useState<ScenarioResponse | null>(null);
  const [scenarioError, setScenarioError] = useState('');
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [showBaseline, setShowBaseline] = useState(false);
  const [horizon, setHorizon] = useState(1);
  const selected =
    response.forecasts.find((row) => row.horizon === horizon) ?? response.forecasts[0];
  const third = response.forecasts.find((row) => row.horizon === 3) ?? response.forecasts.at(-1);
  const replay = response.forecasts.some((row) => row.actual != null);

  useEffect(() => {
    setCapacity(baseCapacity ? Math.round(baseCapacity) : 0);
  }, [baseCapacity, cutoff, trust.code]);
  useEffect(() => {
    setScenario(null);
    if (!Number.isFinite(capacity) || capacity <= 0) {
      setScenarioLoading(false);
      return;
    }
    const controller = new AbortController();
    setScenarioLoading(true);
    setScenarioError('');
    const timer = window.setTimeout(() => {
      request<ScenarioResponse>('/scenarios', {
        method: 'POST',
        body: JSON.stringify({ trust_code: trust.code, cutoff, capacity }),
        signal: controller.signal,
      })
        .then(setScenario)
        .catch((error: Error) => {
          if (error.name !== 'AbortError') setScenarioError(error.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setScenarioLoading(false);
        });
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [capacity, cutoff, trust.code]);

  const scenarioRows = scenario?.forecasts ?? [];
  const minCapacity = Math.max(1, Math.floor((baseCapacity ?? 100) * 0.5));
  const maxCapacity = Math.max(minCapacity + 100, Math.ceil((baseCapacity ?? 100) * 1.5));
  const currentOccupancy =
    latest?.occupied != null && latest?.available
      ? (latest.occupied / latest.available) * 100
      : null;
  const first = response.forecasts[0];
  return (
    <>
      <div className="metrics-grid">
        <MetricCard
          label="Observed occupied beds"
          value={number(latest?.occupied)}
          detail={`${month(cutoff)} · daily average`}
        />
        <MetricCard
          label="Observed occupancy"
          value={number(currentOccupancy, 1)}
          unit="%"
          detail={`${number(baseCapacity)} available beds`}
        />
        <MetricCard
          label="Next-month forecast"
          value={number(first?.prediction)}
          detail={first ? `${month(first.target_month)} · daily average` : 'Forecast unavailable'}
          accent
        >
          <span className="tiny-dot" />
        </MetricCard>
        <MetricCard
          label="Three-month outlook"
          value={number(third?.prediction)}
          detail={
            third
              ? `${number(third.lower)}–${number(third.upper)} beds · 80% interval`
              : 'Forecast unavailable'
          }
        />
      </div>

      <div className="analysis-grid">
        <section className="panel forecast-panel" aria-labelledby="forecast-title">
          <div className="panel-header">
            <div>
              <div className="section-kicker">OCCUPANCY OUTLOOK</div>
              <h2 id="forecast-title">A clearer view of what’s ahead</h2>
              <p>Monthly average daily occupied adult beds</p>
            </div>
            <span className="subtle-pill">1–3 months</span>
          </div>
          <div className="chart-legend">
            <span>
              <i className="legend-line navy" />
              Observed
            </span>
            <span>
              <i className="legend-line grey dashed" />
              Available
            </span>
            <span>
              <i className="legend-line teal" />
              Forecast
            </span>
            <span>
              <i className="legend-area" />
              80% interval
            </span>
            {replay && (
              <span>
                <i className="legend-line blue dashed" />
                Subsequently observed
              </span>
            )}
          </div>
          <ForecastChart
            observations={observations}
            forecasts={response.forecasts}
            cutoff={cutoff}
            showBaseline={showBaseline}
          />
          <div className="chart-footer">
            <label className="check-control">
              <input
                type="checkbox"
                checked={showBaseline}
                onChange={(event) => setShowBaseline(event.target.checked)}
              />
              Compare last-observed baseline
            </label>
            <span>
              <span className="tiny-dot" />
              {replay ? 'Historical replay' : 'Latest available forecast'}
            </span>
          </div>
        </section>

        <section className="panel scenario-panel" aria-labelledby="scenario-title">
          <div className="planner-icon">
            <Icon name="layers" size={21} />
          </div>
          <div className="section-kicker">EXPLORE A SCENARIO</div>
          <h2 id="scenario-title">Plan your capacity</h2>
          <p className="scenario-intro">
            Adjust available beds to see how much room the forecast leaves.
          </p>
          <label className="input-label" htmlFor="capacity">
            Assumed available beds
          </label>
          <div className="capacity-input">
            <input
              id="capacity"
              type="number"
              min="1"
              max="1000000"
              step="1"
              value={capacity || ''}
              onChange={(event) => setCapacity(Number(event.target.value))}
            />
            <span>beds</span>
          </div>
          <input
            aria-label="Capacity slider"
            className="capacity-slider"
            type="range"
            min={minCapacity}
            max={maxCapacity}
            value={Math.max(minCapacity, Math.min(maxCapacity, capacity))}
            onChange={(event) => setCapacity(Number(event.target.value))}
          />
          <div className="slider-labels">
            <span>{number(minCapacity)}</span>
            <button
              className="text-button"
              onClick={() => setCapacity(Math.round(baseCapacity ?? 0))}
            >
              Reset <Icon name="refresh" size={12} />
            </button>
            <span>{number(maxCapacity)}</span>
          </div>
          <div className="scenario-table" aria-live="polite" aria-busy={scenarioLoading}>
            <div className="scenario-heading">
              <span>Forecast month</span>
              <span>Spare beds</span>
            </div>
            {scenarioLoading ? (
              <div className="inline-loading">Updating capacity margins…</div>
            ) : scenarioError ? (
              <p className="inline-error" role="alert">
                {scenarioError}
              </p>
            ) : capacity <= 0 ? (
              <p className="inline-error">Enter a capacity greater than zero.</p>
            ) : (
              scenarioRows.map((row) => (
                <div className="scenario-row" key={row.horizon}>
                  <div>
                    {month(row.target_month)}
                    <small>{percent(row.occupancy_pct)} occupancy</small>
                  </div>
                  <div
                    className={row.margin < 0 ? 'negative' : 'positive'}
                    data-testid={`margin-${row.horizon}`}
                  >
                    {row.margin > 0 ? '+' : ''}
                    {number(row.margin)}
                    <small>
                      {number(row.lower_margin)} to {number(row.upper_margin)}
                    </small>
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="scenario-note">
            <Icon name="info" size={15} />
            <p>
              Predicted occupied beds stay fixed. Ranges reflect forecast uncertainty; negative
              margins indicate a shortfall.
            </p>
          </div>
        </section>
      </div>

      <div className="detail-grid">
        <section className="panel projection-panel" aria-labelledby="projection-title">
          <div className="panel-header">
            <div>
              <div className="section-kicker">MONTH BY MONTH</div>
              <h2 id="projection-title">The forecast in numbers</h2>
            </div>
            <span className="table-unit">Beds, daily average</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Forecast month</th>
                  <th>Prediction</th>
                  <th>80% interval</th>
                  <th>{replay ? 'Actual' : 'Horizon'}</th>
                </tr>
              </thead>
              <tbody>
                {response.forecasts.map((row) => (
                  <tr key={row.horizon}>
                    <td>
                      <strong>{month(row.target_month)}</strong>
                      <small>{modelName(row.model)}</small>
                    </td>
                    <td className="forecast-number">{number(row.prediction, 1)}</td>
                    <td>
                      {number(row.lower, 1)} <span className="muted">—</span> {number(row.upper, 1)}
                    </td>
                    <td>
                      {replay
                        ? number(row.actual, 1)
                        : `+${row.horizon} month${row.horizon > 1 ? 's' : ''}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel-footnote">
            Nominal intervals target 80% coverage. See Model evidence for measured coverage.
            <br />
            Data status: {modelName(response.data_quality_status)} · Version:{' '}
            {response.model_version}
          </div>
        </section>
        <section className="panel explanation-panel" aria-labelledby="explanation-title">
          <div className="panel-header">
            <div>
              <div className="section-kicker">BEHIND THE FORECAST</div>
              <h2 id="explanation-title">What informs the estimate</h2>
            </div>
          </div>
          <div className="horizon-tabs" role="group" aria-label="Explanation horizon">
            {[1, 2, 3].map((item) => (
              <button
                key={item}
                className={item === horizon ? 'active' : ''}
                aria-pressed={item === horizon}
                onClick={() => setHorizon(item)}
              >
                Month {item}
              </button>
            ))}
          </div>
          {selected && (
            <>
              <div className="model-label">
                <Icon name="layers" size={16} />
                {modelName(selected.model)}
              </div>
              <div className="explanation-list">
                {selected.explanation?.length ? (
                  selected.explanation.map((item) => (
                    <div className="explanation-row" key={item.feature}>
                      <span>{item.label || modelName(item.feature)}</span>
                      <strong>
                        {item.contribution != null
                          ? `${item.contribution > 0 ? '+' : ''}${number(item.contribution, 1)} beds`
                          : typeof item.value === 'number'
                            ? number(item.value, 1)
                            : (item.value ?? '—')}
                      </strong>
                    </div>
                  ))
                ) : (
                  <p className="muted small">
                    This baseline uses historical observations directly. No additive feature
                    explanation is available.
                  </p>
                )}
              </div>
              <p className="explanation-note">
                {selected.explanation?.some((item) => item.contribution != null)
                  ? 'Starting occupied beds plus the expected change and all feature effects reconstruct the forecast (subject to rounding). These are not causal effects.'
                  : 'Historical inputs shown for context. Baseline forecasts do not have SHAP contributions.'}
              </p>
            </>
          )}
        </section>
      </div>
    </>
  );
}

function MetricTable({
  rows,
  trustNames,
  showModel = false,
}: {
  rows: Metric[];
  trustNames?: Map<string, string>;
  showModel?: boolean;
}) {
  return (
    <div className="table-scroll">
      <table className="evidence-table">
        <thead>
          <tr>
            <th>{showModel ? 'Model' : trustNames ? 'NHS trust' : 'Period'}</th>
            <th>MAE · beds</th>
            <th>WAPE</th>
            <th>Coverage</th>
            <th>Interval width</th>
            <th>Forecasts</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.code ?? row.model ?? row.period}-${row.horizon}-${index}`}>
              <td>
                <strong>
                  {showModel
                    ? modelName(row.model)
                    : trustNames
                      ? (trustNames.get(row.code ?? '') ?? row.code)
                      : modelName(row.period)}
                </strong>
                {trustNames && <small>{row.code}</small>}
              </td>
              <td>{number(row.mae, 1)}</td>
              <td>{percent(row.wape)}</td>
              <td>{percent(row.coverage == null ? null : row.coverage * 100)}</td>
              <td>{number(row.mean_interval_width, 1)}</td>
              <td>{number(row.n)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <div className="empty-state">No evaluation rows are available for this selection.</div>
      )}
    </div>
  );
}

function Evidence({ evaluation, trusts }: { evaluation: Evaluation; trusts: Trust[] }) {
  const [split, setSplit] = useState('test');
  const [horizon, setHorizon] = useState(1);
  const selected = evaluation.selection.find((row) => row.horizon === horizon);
  const comparison = evaluation.comparison
    .filter((row) => row.horizon === horizon && row.split === split)
    .sort((a, b) => a.mae - b.mae);
  const selectedMetric = comparison.find((row) => row.model === selected?.model);
  const trustNames = new Map(trusts.map((item) => [item.code, item.name]));
  return (
    <>
      <div className="evidence-toolbar">
        <div className="segmented-control" role="group" aria-label="Evaluation split">
          <button
            className={split === 'test' ? 'active' : ''}
            aria-pressed={split === 'test'}
            onClick={() => setSplit('test')}
          >
            Held-out test
          </button>
          <button
            className={split === 'development' ? 'active' : ''}
            aria-pressed={split === 'development'}
            onClick={() => setSplit('development')}
          >
            Development
          </button>
        </div>
        <label className="compact-select">
          Forecast horizon
          <select
            aria-label="Evaluation horizon"
            value={horizon}
            onChange={(event) => setHorizon(Number(event.target.value))}
          >
            <option value={1}>1 month ahead</option>
            <option value={2}>2 months ahead</option>
            <option value={3}>3 months ahead</option>
          </select>
        </label>
      </div>
      <div className="metrics-grid evidence-metrics">
        <MetricCard
          label="Selected model"
          value={modelName(selected?.model)}
          detail={`Selected on development MAE · horizon ${horizon}`}
          accent
        />
        <MetricCard
          label="Mean absolute error"
          value={number(selectedMetric?.mae, 1)}
          unit="beds"
          detail="Lower is better"
        />
        <MetricCard
          label="Measured interval coverage"
          value={number(selectedMetric?.coverage == null ? null : selectedMetric.coverage * 100, 1)}
          unit="%"
          detail="Nominal target: 80%"
        />
        <MetricCard
          label="Mean interval width"
          value={number(selectedMetric?.mean_interval_width, 1)}
          unit="beds"
          detail="Uncertainty span, upper minus lower"
        />
      </div>
      <section className="panel">
        <div className="panel-header">
          <div>
            <div className="section-kicker">BASELINES EARN THEIR PLACE</div>
            <h2>Every model, the same test</h2>
            <p>
              {split === 'test'
                ? 'April 2025–March 2026 · held out from model selection'
                : 'April 2024–March 2025 · rolling model development'}
            </p>
          </div>
          <span className="subtle-pill">Ranked by MAE</span>
        </div>
        <MetricTable rows={comparison} showModel />
        <div className="panel-footnote">
          The best model is chosen separately for each horizon using development MAE. Test results
          do not influence model selection. A baseline can win.
        </div>
      </section>
      <section className="panel evidence-section">
        <div className="panel-header">
          <div>
            <div className="section-kicker">WHERE ERRORS ARE LARGER</div>
            <h2>Results across trusts</h2>
            <p>Held-out test · selected model · sorted by absolute error</p>
          </div>
        </div>
        <MetricTable
          rows={evaluation.by_trust
            .filter((row) => row.horizon === horizon)
            .sort((a, b) => b.mae - a.mae)}
          trustNames={trustNames}
        />
      </section>
      <section className="panel evidence-section">
        <div className="panel-header">
          <div>
            <div className="section-kicker">SEASONAL CHECK</div>
            <h2>Winter and the rest of the year</h2>
            <p>Held-out test · selected model · winter means December–February</p>
          </div>
        </div>
        <MetricTable rows={evaluation.winter.filter((row) => row.horizon === horizon)} />
      </section>
      <div className="method-note">
        <Icon name="info" />
        <p>
          <strong>Read the metrics together.</strong> MAE is measured in occupied beds. WAPE divides
          total absolute error by total observed occupied beds. Coverage is the share of observed
          outcomes inside the interval. A wider interval can improve coverage while being less
          useful for planning.
        </p>
      </div>
    </>
  );
}

function ObservationTable({ observations }: { observations: Observation[] }) {
  return (
    <section className="panel evidence-section">
      <div className="panel-header">
        <div>
          <div className="section-kicker">OBSERVATION QUALITY</div>
          <h2>Reported monthly bed records</h2>
          <p>Missing observations appear as —; reported zero is shown as zero.</p>
        </div>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Month</th>
              <th>Occupied</th>
              <th>Available</th>
              <th>Occupancy</th>
              <th>Data status</th>
            </tr>
          </thead>
          <tbody>
            {[...observations].reverse().map((row) => (
              <tr key={row.month}>
                <td>{month(row.month)}</td>
                <td>{number(row.occupied, 1)}</td>
                <td>{number(row.available, 1)}</td>
                <td>{percent(row.occupancy_pct)}</td>
                <td>{modelName(row.quality_status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Methods({
  trust,
  observations,
  sources,
  meta,
}: {
  trust: Trust;
  observations: Observation[];
  sources: Source[];
  meta: Record<string, unknown>;
}) {
  const complete = observations.filter(
    (row) => row.occupied != null && row.available != null,
  ).length;
  const flagged = observations.filter(
    (row) =>
      row.quality_status && !['ok', 'complete', 'valid', 'observed'].includes(row.quality_status),
  );
  return (
    <>
      <div className="methods-intro">
        <div className="methods-icon">
          <Icon name="database" size={28} />
        </div>
        <div>
          <div className="section-kicker">PUBLIC DATA. INSPECTABLE METHODS.</div>
          <h2>A forecast you can interrogate</h2>
          <p>
            WardCast uses NHS England’s monthly bed statistics. Every result is a retrospective
            estimate at NHS trust level.
          </p>
        </div>
      </div>
      <div className="metrics-grid">
        <MetricCard
          label="Observation window"
          value="48"
          unit="months"
          detail="April 2022–March 2026"
        />
        <MetricCard
          label="Trust records loaded"
          value={number(observations.length)}
          detail={trust.code}
        />
        <MetricCard
          label="Complete bed records"
          value={number(complete)}
          detail="Both occupied and available values present"
        />
        <MetricCard
          label="Records with quality flags"
          value={number(flagged.length)}
          detail="Missing values are never treated as zero"
        />
      </div>
      <div className="methods-grid">
        <section className="panel prose-panel">
          <div className="section-kicker">01 / SOURCE & PROVENANCE</div>
          <h2>The data behind WardCast</h2>
          <p>
            The target is monthly average daily occupied{' '}
            <strong>adult general-and-acute beds</strong>, aggregated by NHS trust. Available beds
            describe reported capacity.
          </p>
          <p>
            Source downloads are retained with a manifest and checksums. The application uses
            revised publications; it cannot reconstruct precisely what was known on the original
            publication day.
          </p>
          <a
            className="source-link"
            href="https://www.england.nhs.uk/statistics/statistical-work-areas/bed-availability-and-occupancy/critical-care-and-general-acute-beds-urgent-and-emergency-care-daily-situation-reports/"
            target="_blank"
            rel="noreferrer"
          >
            NHS England source publications <Icon name="external" size={14} />
          </a>
          <a
            className="source-link"
            href="https://www.england.nhs.uk/terms-and-conditions-2/"
            target="_blank"
            rel="noreferrer"
          >
            NHS England reuse terms <Icon name="external" size={14} />
          </a>
        </section>
        <section className="panel prose-panel">
          <div className="section-kicker">02 / TEMPORAL EVALUATION</div>
          <h2>Respecting the information cutoff</h2>
          <p>
            Historical occupied beds, available capacity, calendar features, and lagged trends
            inform three separate forecast horizons.
          </p>
          <div className="timeline">
            <div>
              <i />
              <strong>Apr 2022–Mar 2024</strong>
              <span>Initial training history</span>
            </div>
            <div>
              <i />
              <strong>Apr 2024–Mar 2025</strong>
              <span>Rolling development & model selection</span>
            </div>
            <div>
              <i />
              <strong>Apr 2025–Mar 2026</strong>
              <span>Held-out rolling test</span>
            </div>
          </div>
          <p className="small">
            At each cutoff, training outcomes must already be observed. Future observed capacity
            never enters forecast features.
          </p>
        </section>
        <section className="panel prose-panel">
          <div className="section-kicker">03 / UNCERTAINTY & EXPLANATIONS</div>
          <h2>An estimate, with room for error</h2>
          <p>
            Prediction intervals target nominal 80% coverage. Actual coverage and interval width are
            published alongside errors, including trust and winter breakdowns.
          </p>
          <p>
            SHAP contributions, when available for the selected model, describe how features affect
            its estimate. They do not establish causes. Simple baselines display their historical
            inputs.
          </p>
          <p>
            Capacity scenarios change the denominator and spare-bed margin while holding forecast
            occupied beds fixed.
          </p>
        </section>
        <section className="panel prose-panel">
          <div className="section-kicker">04 / USE & LIMITATIONS</div>
          <h2>Built for exploration</h2>
          <p>
            Monthly averages smooth over daily and ward-level pressure. Trust mergers, source
            revisions, reporting changes, and the limited history may affect forecasts.
          </p>
          <p>
            Historical replay uses an observation-month cutoff. Reporting delays and revisions mean
            it is not a simulation of a live operational system.
          </p>
          <p>
            No patient records or personal health information are used. WardCast is a portfolio and
            research application, not a clinical or live operational decision system.
          </p>
          {typeof meta.model_version === 'string' && (
            <p className="version-line">
              Artifact version <code>{meta.model_version}</code>
            </p>
          )}
        </section>
      </div>
      <ObservationTable observations={observations} />
      {sources.length > 0 && (
        <section className="panel evidence-section">
          <div className="panel-header">
            <div>
              <div className="section-kicker">AUDIT TRAIL</div>
              <h2>Source manifest</h2>
              <p>
                {number(sources.length)} source records · downloadable source links when available
              </p>
            </div>
          </div>
          <div className="table-scroll manifest-table">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Period</th>
                  <th>SHA-256</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((source, index) => {
                  const url = source.url ?? source.source_url;
                  return (
                    <tr key={source.source_id ?? source.id ?? index}>
                      <td>
                        {url && /^https:\/\//.test(url) ? (
                          <a href={url} target="_blank" rel="noreferrer">
                            {source.filename ??
                              source.source_id ??
                              source.id ??
                              `Source ${index + 1}`}{' '}
                            <Icon name="external" size={12} />
                          </a>
                        ) : (
                          (source.filename ??
                          source.source_id ??
                          source.id ??
                          `Source ${index + 1}`)
                        )}
                      </td>
                      <td>{source.month ? month(source.month) : (source.period ?? '—')}</td>
                      <td>
                        <code title={source.sha256}>
                          {source.sha256 ? `${source.sha256.slice(0, 16)}…` : '—'}
                        </code>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

export default function App() {
  const [view, setView] = useState<View>('overview');
  const [trusts, setTrusts] = useState<Trust[]>([]);
  const [trustCode, setTrustCode] = useState('');
  const [meta, setMeta] = useState<Record<string, unknown>>({});
  const [sources, setSources] = useState<Source[]>([]);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [cutoffs, setCutoffs] = useState<string[]>([]);
  const [cutoff, setCutoff] = useState('');
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [error, setError] = useState('');
  const [evaluationError, setEvaluationError] = useState('');
  const [loading, setLoading] = useState(true);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    Promise.all([
      request<{ trusts: Trust[] }>('/trusts', { signal: controller.signal }),
      request<Record<string, unknown>>('/meta', { signal: controller.signal }),
    ])
      .then(([trustResult, metaResult]) => {
        const list = [...trustResult.trusts].sort((a, b) => a.name.localeCompare(b.name));
        const latestMonth = list.reduce(
          (latest, item) => (item.last_month > latest ? item.last_month : latest),
          '',
        );
        setTrusts(list);
        setMeta(metaResult);
        setTrustCode(
          (current) =>
            current ||
            list.find((item) => item.last_month === latestMonth && (item.latest_available ?? 0) > 0)
              ?.code ||
            list[0]?.code ||
            '',
        );
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    request<Evaluation>('/evaluation', { signal: controller.signal })
      .then(setEvaluation)
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setEvaluationError(err.message);
      });
    request<Source[] | { files: Source[] }>('/sources', { signal: controller.signal })
      .then((result) => setSources(Array.isArray(result) ? result : (result.files ?? [])))
      .catch(() => {
        /* Source publications remain linked in Data & methods. */
      });
    return () => controller.abort();
  }, [retry]);

  useEffect(() => {
    if (!trustCode) return;
    const controller = new AbortController();
    setForecast(null);
    setForecastLoading(true);
    setError('');
    setCutoff('');
    setCutoffs([]);
    setObservations([]);
    Promise.all([
      request<{ observations: Observation[] }>(`/history/${trustCode}`, {
        signal: controller.signal,
      }),
      request<{ cutoffs: string[] }>(`/cutoffs/${trustCode}`, { signal: controller.signal }),
    ])
      .then(([history, available]) => {
        setObservations(history.observations.sort((a, b) => a.month.localeCompare(b.month)));
        const values = [...available.cutoffs].sort();
        setCutoffs(values);
        setCutoff(values.at(-1) ?? '');
        if (!values.length) setForecastLoading(false);
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') {
          setError(err.message);
          setForecastLoading(false);
        }
      });
    return () => controller.abort();
  }, [trustCode, retry]);

  useEffect(() => {
    if (!trustCode || !cutoff) return;
    const controller = new AbortController();
    setForecastLoading(true);
    setError('');
    setForecast(null);
    request<ForecastResponse>(`/forecasts/${trustCode}?cutoff=${encodeURIComponent(cutoff)}`, {
      signal: controller.signal,
    })
      .then(setForecast)
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setForecastLoading(false);
      });
    return () => controller.abort();
  }, [trustCode, cutoff, retry]);

  const trust = trusts.find((item) => item.code === trustCode);
  const titles: Record<View, { eyebrow: string; title: string; subtitle: string }> = {
    overview: {
      eyebrow: 'CAPACITY INTELLIGENCE',
      title: 'Make room for what’s next.',
      subtitle: 'Explore occupancy. Understand uncertainty. Plan with perspective.',
    },
    evidence: {
      eyebrow: 'TRANSPARENT BY DESIGN',
      title: 'The evidence behind the outlook.',
      subtitle: 'Honest benchmarks, measured uncertainty, and a baseline for every model.',
    },
    methods: {
      eyebrow: 'DATA & METHODOLOGY',
      title: 'Know what goes into the forecast.',
      subtitle: 'Public sources, reproducible methods, and clear limits.',
    },
  };
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to main content
      </a>
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            setView('overview');
          }}
          aria-label="WardCast home"
        >
          <div className="brand-mark">
            <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
              <path
                d="M3 18h7l4-11 6 19 4-10h5"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <span>
            WardCast<span className="brand-dot">.</span>
          </span>
        </a>
        <div className="sidebar-caption">AHEAD OF CAPACITY</div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {(
            [
              { id: 'overview', label: 'Capacity overview', icon: 'chart' },
              { id: 'evidence', label: 'Model evidence', icon: 'evidence' },
              { id: 'methods', label: 'Data & methods', icon: 'database' },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              onClick={() => setView(item.id)}
              className={`nav-item${view === item.id ? ' active' : ''}`}
              aria-current={view === item.id ? 'page' : undefined}
            >
              <Icon name={item.icon} />
              {item.label}
              {view === item.id && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="scope-card">
            <span className="scope-dot" />
            <span>Public data. Open methods.</span>
            <p>Monthly capacity forecasts for NHS trusts in England.</p>
          </div>
          <div className="sidebar-footer">
            <span>WARDCAST / 01</span>
            <span>Research edition</span>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <Icon name="chevron" size={12} />
            <strong>
              {view === 'overview'
                ? 'Capacity overview'
                : view === 'evidence'
                  ? 'Model evidence'
                  : 'Data & methods'}
            </strong>
          </div>
          <div className="dataset-badge">
            <span />
            NHS ENGLAND
            <span className="badge-separator" />
            2022–2026
          </div>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <div className="eyebrow page-eyebrow">{titles[view].eyebrow}</div>
              <h1>{titles[view].title}</h1>
              <p>{titles[view].subtitle}</p>
            </div>
            <div className="edition-tag">
              <Icon name="layers" size={15} />
              Retrospective explorer
            </div>
          </div>
          {loading ? (
            <div className="loading-screen" role="status">
              <span className="spinner" />
              Loading public-data workspace…
            </div>
          ) : (
            <>
              {trusts.length > 0 && (
                <div className="selection-bar">
                  <label className="trust-control">
                    <span className="input-label">NHS TRUST</span>
                    <select
                      aria-label="NHS trust"
                      value={trustCode}
                      onChange={(event) => setTrustCode(event.target.value)}
                    >
                      {trusts.map((item) => (
                        <option key={item.code} value={item.code}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="trust-identifier">
                    <span className="input-label">TRUST CODE</span>
                    <span>{trust?.code ?? '—'}</span>
                  </div>
                  <label className="cutoff-control">
                    <span className="input-label">OBSERVATION CUTOFF</span>
                    <select
                      aria-label="Observation cutoff"
                      value={cutoff}
                      onChange={(event) => setCutoff(event.target.value)}
                      disabled={!cutoffs.length}
                    >
                      {!cutoffs.length && <option value="">No cutoffs available</option>}
                      {[...cutoffs].reverse().map((value) => (
                        <option key={value} value={value}>
                          {month(value, 'long')}
                          {value === cutoffs.at(-1) ? ' · latest' : ' · replay'}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
              {error ? (
                <ErrorNotice message={error} retry={() => setRetry((value) => value + 1)} />
              ) : trusts.length === 0 ? (
                <div className="panel empty-state">
                  <Icon name="database" />
                  <h2>No trust data yet</h2>
                  <p>
                    Prepare the public data and demonstration artifacts, then refresh this
                    workspace.
                  </p>
                  <button className="primary-button" onClick={() => setRetry((value) => value + 1)}>
                    Refresh workspace
                  </button>
                </div>
              ) : view === 'overview' ? (
                forecastLoading ? (
                  <div className="loading-screen" role="status">
                    <span className="spinner" />
                    Preparing the occupancy outlook…
                  </div>
                ) : trust && forecast?.forecasts.length ? (
                  <Overview
                    trust={trust}
                    observations={observations}
                    response={forecast}
                    cutoff={cutoff}
                  />
                ) : (
                  <>
                    <div className="panel empty-state">
                      <h2>No eligible forecasts for this trust</h2>
                      <p>
                        Forecasting requires positive adult-bed capacity and sufficient complete
                        history. Reported observations remain available below.
                      </p>
                    </div>
                    <ObservationTable observations={observations} />
                  </>
                )
              ) : view === 'evidence' ? (
                evaluationError ? (
                  <ErrorNotice
                    message={evaluationError}
                    retry={() => {
                      setEvaluationError('');
                      setRetry((value) => value + 1);
                    }}
                  />
                ) : evaluation ? (
                  <Evidence evaluation={evaluation} trusts={trusts} />
                ) : (
                  <div className="loading-screen" role="status">
                    <span className="spinner" />
                    Loading evaluation results…
                  </div>
                )
              ) : trust ? (
                <Methods trust={trust} observations={observations} sources={sources} meta={meta} />
              ) : null}
            </>
          )}
          <footer className="main-footer">
            <div>
              <span className="tiny-dot" />
              Monthly averages · NHS trust level · Revised public data
            </div>
            <span>Built for exploration, with uncertainty in view.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

# Data definition and lineage

## What one record means

One row is one NHS provider trust code and one reporting month. `occupied` is the
published **monthly average daily occupied adult general and acute beds**;
`available` is the matching available-bed count. Counts are source-rounded daily
averages and may be fractional before publication rounding. They are stock
measures, not admissions, daily peak demand, unmet demand, or individual beds.
The derived occupancy percentage is `100 * occupied / available` when available
beds are positive. Maternity, mental-health, paediatric and critical-care beds
are excluded from this adult G&A target.

## Cohort and parsing

WardCast uses provider trusts with a Type 1 A&E department in each publication.
The XLSX parser reads only the Type 1 provider table, supporting the original
and revised layouts. The CSV parser selects `Level=Provider`, `Type=Type 1`, and
the two adult G&A metrics. National, regional, ICB and overlapping all-trust
totals are never treated as additional training examples.

Trust **codes** define separate series. Names may change, but no inference from
similar names joins merged or replacement trusts. Trusts entering or leaving
the source retain their own histories. Eligibility is determined at each origin,
without restricting evaluation to trusts that survive the whole test period.

Missing/suppressed values are null, never zero. Gaps inside a trust's observed
life are explicit null months, so a three-month lag remains three calendar
months even across a missing return. Measurement fields are never forward-filled.
Zero capacity is retained and flagged. Occupied beds above available capacity
are flagged without clamping the published count. See `quality.json` for the
actual audit counts; model eligibility applies additional history requirements.

## Source vintage and reporting delay

`data/source_manifest.json` pins 48 files covering April 2022–March 2026 and their
SHA-256 hashes. Several are revised publications. This is a **retrospective
monthly-observation simulation using revised data**, not a reconstruction of
the numbers publicly known on each historical date. Calendar month cutoffs mean
"observations through this month," not a claim that its return was published
on the month's first or last day. Real releases arrive later; the first horizon
can be a nowcast by the time a source is published. No live forecast is claimed.

Original source files are downloaded into ignored `data/raw/`. The compact,
auditable processed CSV and Parquet panel are included so the demo and tests can
run without contacting NHS England. `wardcast prepare` also creates a local
DuckDB table for SQL inspection. Changed checksums cause a failure rather than
silently changing the benchmark dataset.

## Data-flow contract

`data/raw/` → `data/processed/panel.parquet` → past-only features → chronological
backtests → `artifacts/models.joblib` + `artifacts/demo.json` → same-origin API → UI.

The source manifest and processed quality audit remain available separately from
the model evidence. A failed download, unexpected schema, duplicate key or invalid
month fails preparation with an actionable error. No synthetic observation
replaces missing public evidence.

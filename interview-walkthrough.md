# Explaining WardCast

## A 90-second introduction

“WardCast is a hospital capacity forecasting application built around public NHS
England data. It predicts monthly average daily occupied adult beds for each
eligible trust, one to three months after the observation cutoff. The dashboard
shows forecast uncertainty and lets a user compare the forecast with an assumed
available-bed capacity.

“I built a reproducible ingestion pipeline for two generations of NHS file
layouts, explicitly preserved missing observations, and evaluated five methods
using chronological cutoffs shared across trusts. LightGBM won development
selection at all three horizons and reduced test MAE relative to persistence.
The nominal 80% intervals reached about 76–79% coverage, so the application
shows the measured limitation.

“The result is a trained and tested ML system with a FastAPI backend, a React
interface, saved model artifacts, source checksums, container configuration, and
CI. It is a retrospective demonstration, not a deployed clinical product.”

Adapt this introduction to your own understanding and contributions. Be prepared
to open the implementation and explain each decision rather than memorizing it.

## A five-minute demonstration

1. Open Capacity overview. Explain the trust and observation-month cutoff.
2. Point out occupied beds, available beds, the forecast, and its uncertainty.
3. Enable the last-observed baseline. Explain why a simple benchmark matters.
4. Change the capacity assumption. Occupied-bed predictions stay fixed while
   occupancy percentages and available-bed margins change.
5. Select a historical cutoff. The subsequently observed outcomes provide a
   concrete comparison; none of those future outcomes is a forecast feature.
6. Open Model evidence. Contrast development selection and final test reporting,
   then inspect a particular horizon, trust and winter period.
7. Open Data & methods. Show actual observations, quality flags and source hashes.

## Decisions worth discussing

**Why monthly, not daily?** The collection is described as a daily situation
report, but the selected public files publish monthly averages. Inspecting an
actual file changed the design. The project makes only the claims its data can
support.

**Why boosted trees?** The panel is relatively small and structured. A shallow
pooled model can learn nonlinear seasonal changes across trusts on a CPU. It is
still required to beat persistence, seasonal naive, trailing averages and Ridge.

**Why model changes from the current count?** Current occupancy is a strong
anchor. Learning the next change gives all trusts a useful starting point and
preserves a direct comparison with persistence.

**Where is leakage prevented?** `features.py` constructs calendar-aware lags.
`training_rows` filters on outcome date, not only origin date. The training
loop freezes model choice before test origins and only incorporates outcomes
after they become observable. Preprocessing is fitted inside each fold.

**What does an 80% interval mean here?** It is a nominal prediction band. The
observed coverage is lower than 80% in this test. Serial dependence, service
changes and distribution shifts limit any future coverage claim.

**Why no random train/test split?** It would allow future months from other
trusts, or overlapping forecast labels, to influence earlier forecasts. Shared
calendar cutoffs reflect the intended information flow.

**How does the application use the model?** Training generates a versioned
forecast snapshot and serialized final models. The public demo API reads the
snapshot; it does not need to train or perform arbitrary live inference on every
page view. Saved models are independently checked against the snapshot.

**What would production require?** Authorized timely aggregate feeds, data
contracts and reporting timestamps, facility-specific validation, monitoring,
access controls, incident procedures and operational ownership. Monthly public
data cannot establish the value of a live staffing or discharge intervention.

## Honest limitations to volunteer when relevant

- Four years provide only four annual seasonal cycles; thousands of trust rows
  do not create thousands of independent temporal regimes.
- Monthly averages conceal daily peaks and intra-trust site differences.
- Source revisions prevent an exact historical publication-vintage backtest.
- Occupied beds are constrained by service configuration and capacity; the
  project does not estimate unmet bed demand.
- Interval undercoverage is a result to improve, not hide.
- Better prediction does not prove improved healthcare outcomes or cost savings.

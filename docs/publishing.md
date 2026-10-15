# Publish WardCast on your GitHub account

The repository is self-contained. Publish the project directory, preserving
`DATA_LICENSE.md`, source attribution, model limitations and measured results.
The dataset and dependency authors retain their respective licences.

## Using GitHub CLI

From this project directory, after signing into your own account:

```bash
git init -b main
git add .
git commit -m "Build WardCast capacity forecasting application"
gh repo create wardcast --public --source=. --remote=origin --push
```

If the local repository has already been initialized, skip `git init`. Replace
`--public` with `--private` if preferred. Review `git status` before committing;
the ignore rules exclude virtual environments, raw downloads, local databases,
logs, frontend dependencies and build output. The trained demo artifacts and
compact processed panel are intentionally included.

GitHub Actions will run linting, unit tests, browser tests and a container smoke
test. After the workflow runs successfully, optionally add its verified badge
to the README using your actual repository URL.

Suggested repository description:

> Reproducible NHS hospital capacity forecasts with uncertainty, historical
> replay, explainable ML, and an interactive planning dashboard.

Suggested topics: `machine-learning`, `time-series`, `healthcare`, `forecasting`,
`lightgbm`, `fastapi`, `react`, `explainable-ai`, `mlops`.

## What GitHub hosts

GitHub hosts the source code and documentation. This full FastAPI application
runs locally or in Docker; GitHub Pages alone does not host its Python backend.
The README screenshots provide a preview without promising a hosted service.
No paid deployment or external account is needed for the current release.

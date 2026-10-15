"""Download and normalize the pinned, public NHS bed publications.

The two source formats overlap in scope. Read the Type 1 provider table once;
never concatenate its national/regional totals or the all-trust duplicate sheet.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re

import duckdb
import numpy as np
import openpyxl
import pandas as pd
import requests

METRICS = {"Adult G&A beds occupied": "occupied", "Adult G&A beds available": "available"}
MISSING_TOKENS = {"", "-", "..", ":", "[z]", "[x]", "[c]", "[u]", "n/a", "nan", "none"}


def _number(value: object) -> float:
    if value is None or str(value).strip().lower() in MISSING_TOKENS:
        return float("nan")
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        raise ValueError(f"Unrecognized numeric token: {value!r}") from None
    return number if np.isfinite(number) and number >= 0 else float("nan")


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def download(root: Path, *, workers: int = 4) -> dict:
    """Download pinned files; existing/checksummed files are reused or verified."""
    manifest_path = root / "data/source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    raw = root / "data/raw"
    raw.mkdir(parents=True, exist_ok=True)

    def fetch(source: dict) -> dict:
        target = raw / source["filename"]
        if not target.exists():
            response = requests.get(source["url"], timeout=(10, 90),
                                    headers={"User-Agent": "WardCast/1.0 public-data-research"})
            response.raise_for_status()
            body = response.content
            if len(body) < 1000 or body.lstrip().startswith((b"<", b"<!")):
                raise RuntimeError(f"Source returned a challenge or invalid file: {source['url']}")
            temporary = target.with_suffix(target.suffix + ".part")
            temporary.write_bytes(body)
            temporary.replace(target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if source.get("sha256") and source["sha256"] != digest:
            raise ValueError(f"Source checksum changed: {target.name}. Do not silently replace the source vintage.")
        print(f"Verified {source['month']}: {target.name}", flush=True)
        return {**source, "sha256": digest, "bytes": target.stat().st_size}

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as pool:
        manifest["files"] = list(pool.map(fetch, manifest["files"]))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def parse_csv(path: Path, month: str, source_id: str) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    raw.columns = [str(c).strip() for c in raw.columns]
    required = {"Period", "Level", "Region", "Org Code", "Org Name", "Metric", "Type", "Value"}
    if not required.issubset(raw.columns):
        raise ValueError(f"Unexpected CSV schema in {path.name}: {list(raw.columns)}")
    raw = raw[(raw["Level"].str.strip() == "Provider") &
              (raw["Type"].str.strip() == "Type 1") & raw["Metric"].isin(METRICS)].copy()
    if raw.empty:
        raise ValueError(f"No Type 1 adult bed observations in {path.name}")
    periods = pd.to_datetime(raw["Period"], dayfirst=True, errors="raise").dt.to_period("M")
    if not (periods == pd.Period(month, freq="M")).all():
        raise ValueError(f"Source month does not match manifest in {path.name}")
    if raw.duplicated(["Org Code", "Metric"]).any():
        raise ValueError(f"Duplicate provider/metric in {path.name}")
    raw["value"] = raw["Value"].map(_number)
    result = raw.pivot(index=["Org Code", "Org Name", "Region"], columns="Metric", values="value")
    result = result.rename(columns=METRICS).reset_index().rename(
        columns={"Org Code": "code", "Org Name": "name", "Region": "region"})
    for field in ("occupied", "available"):
        if field not in result:
            result[field] = np.nan
    result["month"] = month
    result["source_id"] = source_id
    return result[["code", "name", "region", "month", "occupied", "available", "source_id"]]


def parse_xlsx(path: Path, month: str, source_id: str) -> pd.DataFrame:
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        sheets = [s for s in workbook if "type 1" in s.title.lower()]
        if len(sheets) != 1:
            raise ValueError(f"Expected one Type 1 sheet in {path.name}; found {[s.title for s in sheets]}")
        rows = list(sheets[0].values)
        header = None
        # Older books omit the first four column labels; revised books have
        # separate metric and provider headers with an ICB table in between.
        revised = any("Org Code" in [_clean(v) for v in row] for row in rows)
        identity = None if revised else {"Region": 1, "Trust Name": 2, "Code": 3}
        records = []
        for values in rows:
            cleaned = [_clean(v) for v in values]
            if "Adult G&A beds occupied" in cleaned:
                header = {value: i for i, value in enumerate(cleaned) if value}
                continue
            if "Org Code" in cleaned and "Org Name" in cleaned:
                identity = {"Region": cleaned.index("Region"), "Trust Name": cleaned.index("Org Name"),
                            "Code": cleaned.index("Org Code")}
                continue
            if header is None or identity is None:
                continue
            code = cleaned[identity["Code"]]
            if not re.fullmatch(r"[A-Z0-9]{3}", code) or code == "ENG":
                continue
            record = {"code": code, "name": cleaned[identity["Trust Name"]],
                      "region": cleaned[identity["Region"]], "month": month, "source_id": source_id}
            for metric, key in METRICS.items():
                record[key] = _number(values[header[metric]])
            records.append(record)
        if not records:
            raise ValueError(f"No provider records parsed from {path.name}")
        return pd.DataFrame(records)
    finally:
        workbook.close()


def validate_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Preserve missingness; trust codes, not names, are the series identities."""
    result = panel.copy()
    if result.duplicated(["code", "month"]).any():
        bad = result.loc[result.duplicated(["code", "month"], keep=False), ["code", "month"]]
        raise ValueError(f"Duplicate trust/month observations: {bad.head().to_dict('records')}")
    result["month"] = pd.to_datetime(result["month"]).dt.strftime("%Y-%m-01")
    for column in ("occupied", "available"):
        result[column] = pd.to_numeric(result[column], errors="raise")
        result.loc[~np.isfinite(result[column]) | (result[column] < 0), column] = np.nan
    # Insert gaps *inside* a code's observed life only. Never join old and new codes.
    groups = []
    for code, frame in result.groupby("code", sort=True):
        frame = frame.sort_values("month").set_index("month")
        months = pd.date_range(frame.index.min(), frame.index.max(), freq="MS").strftime("%Y-%m-%d")
        frame = frame.reindex(months).rename_axis("month").reset_index()
        frame["code"] = code
        for column in ("name", "region"):
            frame[column] = frame[column].ffill()  # Metadata only, never measurements.
        frame["source_id"] = frame["source_id"].fillna("")
        groups.append(frame)
    result = pd.concat(groups, ignore_index=True)
    result["quality_status"] = "observed"
    missing = result[["occupied", "available"]].isna().any(axis=1)
    result.loc[missing, "quality_status"] = "missing"
    result.loc[~missing & (result["available"] == 0), "quality_status"] = "zero_capacity"
    result.loc[~missing & (result["occupied"] > result["available"]), "quality_status"] = "occupied_exceeds_available"
    result["occupancy_pct"] = np.where(result["available"] > 0,
                                        result["occupied"] / result["available"] * 100, np.nan)
    return result.sort_values(["code", "month"]).reset_index(drop=True)


def prepare(root: Path) -> pd.DataFrame:
    manifest = json.loads((root / "data/source_manifest.json").read_text())
    frames = []
    for source in manifest["files"]:
        path = root / "data/raw" / source["filename"]
        if not path.exists():
            raise FileNotFoundError(f"Missing {path.name}. Run `wardcast download` first.")
        if source.get("sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Source checksum changed: {path.name}")
        parser = parse_csv if path.suffix == ".csv" else parse_xlsx
        frames.append(parser(path, source["month"], source["filename"]))
    panel = validate_panel(pd.concat(frames, ignore_index=True))
    # Use consistent display casing without changing trust-code identity.
    panel["region"] = panel["region"].str.title()
    out = root / "data/processed"
    out.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out / "panel.parquet", index=False)
    panel.to_csv(out / "panel.csv", index=False)
    with duckdb.connect(str(out / "wardcast.duckdb")) as connection:
        connection.register("source_panel", panel)
        connection.execute("CREATE OR REPLACE TABLE monthly_beds AS SELECT * FROM source_panel")
        assert connection.execute("SELECT COUNT(*) FROM monthly_beds").fetchone()[0] == len(panel)
    names = panel.groupby("code")["name"].agg(lambda x: sorted(set(x)))
    quality = {
        "cohort": "Provider trusts with a Type 1 A&E department in each source month",
        "rows": len(panel), "trusts": int(panel["code"].nunique()),
        "months": int(panel["month"].nunique()), "data_start": panel["month"].min(),
        "data_end": panel["month"].max(), "status_counts": panel["quality_status"].value_counts().to_dict(),
        "missing_values": panel[["occupied", "available"]].isna().sum().to_dict(),
        "name_variants": {code: values for code, values in names.items() if len(values) > 1},
        "series_policy": "No code merging. Gaps are null; discontinued series retain their end date. Names may change within a code.",
        "definition": "Monthly average daily occupied/available adult general and acute beds; not daily peaks or unmet demand.",
        "vintage_note": manifest["vintage_note"],
    }
    (out / "quality.json").write_text(json.dumps(quality, indent=2) + "\n")
    print(f"Prepared {len(panel):,} trust-month rows, {quality['trusts']} trusts, {quality['months']} months.", flush=True)
    return panel

from pathlib import Path
import pandas as pd
import pytest

from wardcast.data import parse_csv, parse_xlsx, validate_panel


def row(code="ABC", month="2024-01-01", occupied=80, available=100):
    return dict(code=code, name="Example trust", region="London", month=month,
                occupied=occupied, available=available, source_id="fixture")


def test_gaps_are_null_and_zero_is_not_missing():
    panel = validate_panel(pd.DataFrame([row(occupied=0), row(month="2024-03-01")]))
    assert panel.iloc[0].occupied == 0
    assert panel.iloc[0].quality_status == "observed"
    assert pd.isna(panel.iloc[1].occupied)
    assert panel.iloc[1].quality_status == "missing"


def test_duplicate_trust_month_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        validate_panel(pd.DataFrame([row(), row()]))


def test_trust_code_change_starts_new_series():
    panel = validate_panel(pd.DataFrame([row("OLD"), row("NEW", "2024-03-01")]))
    assert len(panel) == 2
    assert set(panel.code) == {"OLD", "NEW"}


def test_occupancy_above_capacity_is_flagged_not_clipped():
    panel = validate_panel(pd.DataFrame([row(occupied=102)]))
    assert panel.iloc[0].occupied == 102
    assert panel.iloc[0].quality_status == "occupied_exceeds_available"


def test_csv_filters_aggregates_and_preserves_missing(tmp_path: Path):
    path = tmp_path / "beds.csv"
    path.write_text("Period,Level,Region,Org Code,Org Name,Metric,Type,Value\n"
                    "01/01/2024,Provider,London,ABC,Example,Adult G&A beds occupied,Type 1,[x]\n"
                    "01/01/2024,Provider,London,ABC,Example,Adult G&A beds available,Type 1,100\n"
                    "01/01/2024,National,,ENG,England,Adult G&A beds occupied,Type 1,90000\n")
    panel = parse_csv(path, "2024-01-01", "fixture")
    assert len(panel) == 1
    assert pd.isna(panel.iloc[0].occupied)
    assert panel.iloc[0].available == 100
    with pytest.raises(ValueError, match="month"):
        parse_csv(path, "2024-02-01", "fixture")


@pytest.mark.parametrize("revised", [False, True])
def test_xlsx_original_and_revised_provider_tables(tmp_path: Path, revised: bool):
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.title = "Jan 2024 type 1 acute trusts"
    sheet.append([None, None, None, None, "Adult G&A beds available", "Adult G&A beds occupied"])
    sheet.append([None, None, "ENGLAND", None, 90000, 80000])
    if revised:
        sheet.append([None, "Region", "ICB Code", "ICB Name"])
        sheet.append([None, "LONDON", "QAA", "Not a provider", 5000, 4500])
        sheet.append([None, "Region", "Org Code", "Org Name"])
        sheet.append([None, "LONDON", "ABC", "Example Trust", 100, 80])
    else:
        # The actual April 2023 source omits these identity column labels.
        sheet.append([None, "LONDON", "Example Trust", "ABC", 100, 80])
    path = tmp_path / "source.xlsx"
    book.save(path)
    panel = parse_xlsx(path, "2024-01-01", "fixture")
    assert len(panel) == 1
    assert panel.iloc[0].code == "ABC"
    assert panel.iloc[0].occupied == 80
    assert panel.iloc[0].available == 100

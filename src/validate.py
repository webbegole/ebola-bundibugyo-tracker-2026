"""
Pre-commit validator for the Ebola tracker CSVs.

Runs structural and invariant checks on data/timeseries.csv,
data/country_breakdown.csv, and data/declarations.csv. Exits 0 on
success, non-zero on any failure with a human-readable explanation
of what's wrong.

Invoked by the scheduled task before every git commit. If validation
fails, the task skips the commit and writes a
_commit-blocked-YYYY-MM-DD-HHMM.md report to the project folder root
with this script's stderr captured for review.

Usage:
    python3 src/validate.py
    # exit 0 = clean, exit 1 = at least one failure

Design principles:
- Each check is independent and reports all failures, not just the first.
- Failures are dated by which file and which row, so a human can fix
  the underlying CSV without re-running the validator to bisect.
- The validator never modifies files. It only reads.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"

TIMESERIES = DATA / "timeseries.csv"
BREAKDOWN = DATA / "country_breakdown.csv"
DECLARATIONS = DATA / "declarations.csv"

# Expected column orders. Order matters because index.html and
# build_xlsx.py both depend on a stable schema.
EXPECTED_TIMESERIES_COLS = [
    "report_date",
    "suspected_global",
    "confirmed_global",
    "total_global",
    "suspected_deaths_global",
    "confirmed_deaths_global",
    "recovered_global",
    "primary_source",
    "source_timestamp",
]
EXPECTED_BREAKDOWN_COLS = [
    "date",
    "country",
    "suspected",
    "confirmed",
    "suspected_deaths",
    "confirmed_deaths",
    "recovered",
    "primary_source",
    "source_timestamp",
]
EXPECTED_DECLARATIONS_COLS = [
    "country",
    "first_report_date",
    "case_status",
    "cdc_advisory",
    "cdc_url",
    "cdc_travel_notice_level",
    "cdc_travel_notice_url",
    "who_status",
    "who_url",
    "notes",
]

# Columns in timeseries.csv that are cumulative and therefore must be
# monotonically non-decreasing across rows (the no-dip rule).
CUMULATIVE_TIMESERIES_COLS = [
    "suspected_global",
    "confirmed_global",
    "total_global",
    "suspected_deaths_global",
    "confirmed_deaths_global",
    "recovered_global",
]

# Columns in country_breakdown.csv that are cumulative per country.
CUMULATIVE_BREAKDOWN_COLS = [
    "suspected",
    "confirmed",
    "suspected_deaths",
    "confirmed_deaths",
    "recovered",
]

# No-dip rule exemptions. Per METHODOLOGY.md "MoH methodology-change carve-out":
# when the official surveillance source (DRC MoH / Uganda MoH) formally announces
# a definitional cleanup (e.g., suspected cases that subsequently tested negative
# are removed after a lab-capacity ramp-up), the two-source threshold is waived
# and the dip is applied. The named columns are skipped by the no-dip check on
# the named date, and the new lower baseline takes effect from that row onward.
# Each entry must have a matching NOTES bullet documenting the announcement and
# the figures applied.
NO_DIP_EXEMPTIONS_TIMESERIES = {
    # 2026-05-30: DRC MoH announced removal of ~700 suspected cases that tested
    # negative for Ebola after lab capacity ramp-up; suspected-deaths column
    # zeroed as part of the same cleanup. Source: BNO @BNOFeed Daily Ebola
    # Update May 30 graphic carrying DRC MoH attribution.
    "2026-05-30": {"suspected_global", "total_global", "suspected_deaths_global"},
    # 2026-05-31: completion of the DRC MoH lab-capacity ramp-up cleanup, dated to
    # WHO Weekly Sitrep 03 (data as of 31 May 2026), which reconciles DRC to 321
    # confirmed / 48 deaths / 116 suspected. Reconciled 2026-06-08 (Web-directed)
    # from the prior BNO running count (225 conf / 447 sus); the suspected total
    # drops from 349 (May 30) to 116 as test-negatives are removed and cases move
    # from suspected to confirmed. WHO Weekly Sitrep is source #1 (gold standard).
    # This carve-out moved here from 2026-06-01, which now holds the same
    # post-cleanup level (no dip) after the reconciliation.
    "2026-05-31": {"suspected_global", "total_global"},
}
NO_DIP_EXEMPTIONS_BREAKDOWN = {
    # (date, country) -> set of exempt column names
    ("2026-05-30", "DRC"): {"suspected", "suspected_deaths"},
    ("2026-05-31", "DRC"): {"suspected"},
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fail(failures: list, where: str, msg: str) -> None:
    failures.append(f"  - {where}: {msg}")


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = []
        for raw in reader:
            if not any(cell.strip() for cell in raw):
                continue  # skip blank lines
            rows.append(dict(zip(header, raw)))
        return header, rows


def parse_int(cell: str) -> int | None:
    """Treat blank/None as None. Parse integers strictly."""
    if cell is None:
        return None
    s = cell.strip()
    if s == "":
        return None
    return int(s)  # raises ValueError if malformed; caller catches


def check_schema(name: str, header: list[str], expected: list[str], failures: list) -> bool:
    """Header must match expected columns in order. Returns True if OK."""
    if header == expected:
        return True
    extra = [c for c in header if c not in expected]
    missing = [c for c in expected if c not in header]
    reorder = header != expected and not extra and not missing
    if reorder:
        fail(failures, name, f"columns present but in wrong order. Got {header}, expected {expected}")
    else:
        if missing:
            fail(failures, name, f"missing columns: {missing}")
        if extra:
            fail(failures, name, f"unexpected columns: {extra}")
    return False


def validate_timeseries(failures: list) -> list[dict]:
    header, rows = read_csv(TIMESERIES)
    schema_ok = check_schema("timeseries.csv", header, EXPECTED_TIMESERIES_COLS, failures)
    if not schema_ok or not rows:
        return rows

    # Date format + strict-ascending uniqueness.
    prev_date = None
    for i, r in enumerate(rows, start=2):  # row 2 is first data row in the file
        d = r["report_date"].strip()
        if not DATE_RE.match(d):
            fail(failures, f"timeseries.csv row {i}", f"report_date not YYYY-MM-DD: {d!r}")
            continue
        if prev_date is not None and d <= prev_date:
            fail(failures, f"timeseries.csv row {i}",
                 f"report_date {d} not strictly after previous {prev_date} "
                 "(rows must be in chronological order and unique)")
        prev_date = d

    # Parse numerics, check non-negative, check total = sus + conf.
    parsed = []
    for i, r in enumerate(rows, start=2):
        try:
            sus = parse_int(r["suspected_global"])
            conf = parse_int(r["confirmed_global"])
            total = parse_int(r["total_global"])
            deaths = parse_int(r["suspected_deaths_global"])
            conf_deaths = parse_int(r["confirmed_deaths_global"])
            recovered = parse_int(r["recovered_global"])
        except ValueError as e:
            fail(failures, f"timeseries.csv row {i}", f"non-numeric in cumulative column: {e}")
            parsed.append(None)
            continue
        for label, v in (("suspected_global", sus), ("confirmed_global", conf),
                         ("total_global", total), ("suspected_deaths_global", deaths),
                         ("confirmed_deaths_global", conf_deaths),
                         ("recovered_global", recovered)):
            if v is not None and v < 0:
                fail(failures, f"timeseries.csv row {i}", f"{label} is negative: {v}")
        # If all three of sus/conf/total are present, total must equal sus + conf.
        # (recovered is tracked separately and is NOT part of total_global.)
        if sus is not None and conf is not None and total is not None:
            if total != sus + conf:
                fail(failures, f"timeseries.csv row {i} ({r['report_date']})",
                     f"total_global ({total}) != suspected_global ({sus}) + confirmed_global ({conf})")
        # Recovered plus confirmed deaths cannot exceed confirmed cases: you
        # cannot have resolved more cases than were ever confirmed.
        if recovered is not None and conf is not None and conf_deaths is not None:
            if recovered + conf_deaths > conf:
                fail(failures, f"timeseries.csv row {i} ({r['report_date']})",
                     f"recovered_global ({recovered}) + confirmed_deaths_global ({conf_deaths}) "
                     f"exceeds confirmed_global ({conf}) — implies negative active cases")
        parsed.append({"row": i, "date": r["report_date"], "sus": sus,
                       "conf": conf, "total": total, "deaths": deaths,
                       "conf_deaths": conf_deaths, "recovered": recovered})

    # Cumulative non-decreasing check (the no-dip rule).
    # Rows listed in NO_DIP_EXEMPTIONS_TIMESERIES bypass the check on the named
    # columns; the new lower baseline becomes the comparison point for subsequent
    # rows. See METHODOLOGY.md "MoH methodology-change carve-out".
    for col_key, col_name in (("sus", "suspected_global"), ("conf", "confirmed_global"),
                              ("total", "total_global"), ("deaths", "suspected_deaths_global"),
                              ("conf_deaths", "confirmed_deaths_global"),
                              ("recovered", "recovered_global")):
        prev = None
        prev_date = None
        for p in parsed:
            if p is None:
                continue
            v = p[col_key]
            if v is None:
                continue
            exempt = col_name in NO_DIP_EXEMPTIONS_TIMESERIES.get(p["date"], set())
            if prev is not None and v < prev and not exempt:
                fail(failures, f"timeseries.csv row {p['row']} ({p['date']})",
                     f"{col_name} decreased from {prev} (row dated {prev_date}) to {v} — "
                     "no-dip rule. Hold higher value and log dip in notes.md until "
                     "a second high-value source corroborates, OR add an entry to "
                     "NO_DIP_EXEMPTIONS_TIMESERIES if this is a MoH methodology-change "
                     "carve-out per METHODOLOGY.md.")
            prev = v
            prev_date = p["date"]

    return rows


def validate_breakdown(failures: list) -> list[dict]:
    header, rows = read_csv(BREAKDOWN)
    schema_ok = check_schema("country_breakdown.csv", header, EXPECTED_BREAKDOWN_COLS, failures)
    if not schema_ok or not rows:
        return rows

    # Date format + uniqueness of (date, country) pairs.
    seen = set()
    for i, r in enumerate(rows, start=2):
        d = r["date"].strip()
        c = r["country"].strip()
        if not DATE_RE.match(d):
            fail(failures, f"country_breakdown.csv row {i}", f"date not YYYY-MM-DD: {d!r}")
            continue
        if not c:
            fail(failures, f"country_breakdown.csv row {i}", "country is blank")
            continue
        key = (d, c)
        if key in seen:
            fail(failures, f"country_breakdown.csv row {i}",
                 f"duplicate (date, country) pair: {key}")
        seen.add(key)

    # Parse numerics and check non-negative.
    parsed = []
    for i, r in enumerate(rows, start=2):
        try:
            sus = parse_int(r["suspected"])
            conf = parse_int(r["confirmed"])
            sus_d = parse_int(r["suspected_deaths"])
            conf_d = parse_int(r["confirmed_deaths"])
            rec = parse_int(r["recovered"])
        except ValueError as e:
            fail(failures, f"country_breakdown.csv row {i}", f"non-numeric: {e}")
            parsed.append(None)
            continue
        for label, v in (("suspected", sus), ("confirmed", conf),
                         ("suspected_deaths", sus_d), ("confirmed_deaths", conf_d),
                         ("recovered", rec)):
            if v is not None and v < 0:
                fail(failures, f"country_breakdown.csv row {i}", f"{label} is negative: {v}")
        parsed.append({"row": i, "date": r["date"], "country": r["country"].strip(),
                       "sus": sus, "conf": conf, "sus_d": sus_d, "conf_d": conf_d,
                       "rec": rec})

    # Per-country cumulative non-decreasing.
    # (date, country) pairs in NO_DIP_EXEMPTIONS_BREAKDOWN bypass the check on
    # the named columns. See METHODOLOGY.md "MoH methodology-change carve-out".
    by_country = {}
    for p in parsed:
        if p is None:
            continue
        by_country.setdefault(p["country"], []).append(p)
    for country, prows in by_country.items():
        prows.sort(key=lambda x: x["date"])
        for col_key, col_name in (("sus", "suspected"), ("conf", "confirmed"),
                                  ("sus_d", "suspected_deaths"), ("conf_d", "confirmed_deaths"),
                                  ("rec", "recovered")):
            prev = None
            prev_date = None
            for p in prows:
                v = p[col_key]
                if v is None:
                    continue
                exempt = col_name in NO_DIP_EXEMPTIONS_BREAKDOWN.get((p["date"], country), set())
                if prev is not None and v < prev and not exempt:
                    fail(failures, f"country_breakdown.csv {country} row {p['row']} ({p['date']})",
                         f"{col_name} decreased from {prev} (dated {prev_date}) to {v} — "
                         "per-country no-dip violation (add NO_DIP_EXEMPTIONS_BREAKDOWN entry "
                         "if MoH methodology-change carve-out).")
                prev = v
                prev_date = p["date"]

    return parsed


def cross_check_latest_date(ts_rows: list[dict], bd_parsed: list[dict], failures: list) -> None:
    """On the most recent date in timeseries.csv, country sums must equal global totals
    for the columns that have a clean mapping (suspected, confirmed)."""
    if not ts_rows:
        return
    last_ts = ts_rows[-1]
    last_date = last_ts["report_date"].strip()
    try:
        global_sus = parse_int(last_ts["suspected_global"])
        global_conf = parse_int(last_ts["confirmed_global"])
        global_rec = parse_int(last_ts["recovered_global"])
    except ValueError:
        return

    bd_on_date = [p for p in bd_parsed if p is not None and p["date"] == last_date]
    if not bd_on_date:
        fail(failures, f"cross-check {last_date}",
             "country_breakdown.csv has no rows for the latest timeseries.csv date — "
             "add per-country rows for the latest date even if contributions are unchanged.")
        return

    sum_sus = sum((p["sus"] or 0) for p in bd_on_date)
    sum_conf = sum((p["conf"] or 0) for p in bd_on_date)

    if global_sus is not None and sum_sus != global_sus:
        countries = ", ".join(f"{p['country']}={p['sus'] or 0}" for p in bd_on_date)
        fail(failures, f"cross-check {last_date}",
             f"suspected sum across countries ({sum_sus}: {countries}) "
             f"!= timeseries suspected_global ({global_sus})")
    if global_conf is not None and sum_conf != global_conf:
        countries = ", ".join(f"{p['country']}={p['conf'] or 0}" for p in bd_on_date)
        fail(failures, f"cross-check {last_date}",
             f"confirmed sum across countries ({sum_conf}: {countries}) "
             f"!= timeseries confirmed_global ({global_conf})")
    # Recovered cross-check: only enforce when every country on the latest date
    # carries a recovered figure. A blank on any country means the global total
    # can't be reconstructed from the breakdown that day, so skip rather than
    # false-alarm (recovered has documented backfill gaps on some earlier days).
    if global_rec is not None and all(p["rec"] is not None for p in bd_on_date):
        sum_rec = sum(p["rec"] for p in bd_on_date)
        if sum_rec != global_rec:
            countries = ", ".join(f"{p['country']}={p['rec']}" for p in bd_on_date)
            fail(failures, f"cross-check {last_date}",
                 f"recovered sum across countries ({sum_rec}: {countries}) "
                 f"!= timeseries recovered_global ({global_rec})")


def validate_declarations(failures: list) -> None:
    header, rows = read_csv(DECLARATIONS)
    schema_ok = check_schema("declarations.csv", header, EXPECTED_DECLARATIONS_COLS, failures)
    if not schema_ok or not rows:
        return
    seen_countries = set()
    for i, r in enumerate(rows, start=2):
        c = r["country"].strip()
        if not c:
            fail(failures, f"declarations.csv row {i}", "country is blank")
            continue
        if c in seen_countries:
            fail(failures, f"declarations.csv row {i}", f"duplicate country: {c}")
        seen_countries.add(c)
        d = r["first_report_date"].strip()
        if d and not DATE_RE.match(d):
            fail(failures, f"declarations.csv row {i} ({c})",
                 f"first_report_date not YYYY-MM-DD: {d!r}")


def main() -> int:
    failures: list[str] = []
    ts_rows = validate_timeseries(failures)
    bd_parsed = validate_breakdown(failures)
    cross_check_latest_date(ts_rows, bd_parsed, failures)
    validate_declarations(failures)

    if failures:
        print("VALIDATION FAILED", file=sys.stderr)
        print(f"{len(failures)} issue(s):", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print("VALIDATION OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

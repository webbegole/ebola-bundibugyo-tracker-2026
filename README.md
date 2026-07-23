# 2026 Ebola (Bundibugyo) Outbreak Tracker

By [Web Begole](https://www.linkedin.com/in/webbegole/) ([@web_begole](https://x.com/web_begole) on X).

A daily time series of the 2026 Ebola outbreak in DRC and Uganda, compiled from official public-health sources for academic use. Aggregate counts only. No individuals named. No medical advice.

Live site: [webbegole.github.io/ebola-bundibugyo-tracker-2026](https://webbegole.github.io/ebola-bundibugyo-tracker-2026/)

## What's in the repo

- `data/timeseries.csv` — the main daily series. Global headline totals only. One row per Report Date.
- `data/country_breakdown.csv` — per-country detail in long format (DRC, Uganda, future reporters). Grows as new countries report cases.
- `data/declarations.csv` — per-country CDC advisory and WHO declaration status with primary-source URLs. Updates when declarations change or new countries are added.
- `data/story.md` — narrative summary: "Story so far" plus "Latest update". Updated when material developments warrant.
- `data/notes.md` — methodology decisions, source-conflict resolutions, and the revision log. Append-only and dated. The git history of this file is the canonical audit trail.
- `METHODOLOGY.md` — the playbook: source preference order, lookback policy, no-dip rule, chart conventions.
- `src/generate_charts.py` — reads the CSVs and renders the PNG charts.
- `src/build_xlsx.py` — rebuilds a convenience XLSX export from the CSVs.
- `src/validate.py` — pre-commit gate. Checks CSV schemas, monotonic cumulative columns (the no-dip rule), `total = suspected + confirmed`, country sums equal global totals on the latest date, and date format and uniqueness. Run with `python3 src/validate.py`; exit 0 = clean, non-zero = at least one failure with a row-level explanation.
- `outputs/` — generated charts and the XLSX export. Build artifacts.

## Latest charts

The most recent charts are in `outputs/` with date-prefixed filenames:

- `outputs/YYYY-MM-DD_ebola-cases-7d-rolling-sum.png`
- `outputs/YYYY-MM-DD_ebola-deaths-7d-rolling-sum.png`
- `outputs/YYYY-MM-DD_ebola-active-cases.png` — daily new confirmed cases (up) against recoveries and deaths (down), with a cumulative active ("live") cases line: confirmed minus recovered minus confirmed deaths.
- `outputs/YYYY-MM-DD_ebola-active-wow.png` — week-over-week percent change in active cases: the mean active level over the last 7 days versus the mean over the prior 7 days. Above zero, the live caseload is still growing; the two averaging windows smooth out daily spikes.

Where `YYYY-MM-DD` is the most recent Report Date in `data/timeseries.csv`. A doubling-time chart is implemented in `src/generate_charts.py` but not currently published; early confirmed-case figures are heavily revised by WHO Sitrep reconciliation, which makes the trailing-window fit unstable. It will be re-enabled once the data is less provisional.

## Data schemas

### `timeseries.csv`

| Column | Type | Definition |
|---|---|---|
| `report_date` | `YYYY-MM-DD` | The calendar day this row was added. |
| `suspected_global` | int | Cumulative suspected cases across all reporting countries. |
| `confirmed_global` | int | Cumulative lab-confirmed cases (PCR at INRB or partner labs). |
| `total_global` | int | `suspected_global + confirmed_global`. |
| `suspected_deaths_global` | int | Cumulative suspected deaths across all reporting countries. |
| `confirmed_deaths_global` | int | Cumulative lab-confirmed deaths across all reporting countries. |
| `recovered_global` | int (nullable) | Cumulative recovered/discharged confirmed cases across all reporting countries. Blank on days no source published a figure; charts forward-fill those gaps. Not part of `total_global`. |
| `primary_source` | string | Short citation, including the source's "as of" date. |
| `source_timestamp` | `YYYY-MM-DD` | The date the source itself uses for the data. Makes reporting lag visible. |

Per-country figures (DRC, Uganda, future reporters) live in `country_breakdown.csv`.

### `country_breakdown.csv`

| Column | Type | Definition |
|---|---|---|
| `date` | `YYYY-MM-DD` | Matches the main timeseries `report_date`. |
| `country` | string | Reporting country (DRC, Uganda, etc.). |
| `suspected` | int (nullable) | Country-specific cumulative suspected cases. Blank if source doesn't publish. |
| `confirmed` | int (nullable) | Country-specific cumulative confirmed cases. |
| `suspected_deaths` | int (nullable) | Country-specific cumulative suspected deaths. |
| `confirmed_deaths` | int (nullable) | Country-specific cumulative confirmed deaths. Blank if not broken out. |
| `recovered` | int (nullable) | Country-specific cumulative recovered/discharged confirmed cases. Blank if the source didn't publish a figure that day. |
| `primary_source` | string | Country-level source citation. |
| `source_timestamp` | `YYYY-MM-DD` | Source's "as of" date. |

### `notes.md`

Plain markdown list. Each bullet is dated and attributed. New bullets are appended; existing bullets are not edited. See `METHODOLOGY.md` for the rules around when a bullet is added.

## Build

```bash
pip install -r requirements.txt   # or: pip install -e .
python3 src/generate_charts.py    # regenerates the four PNGs in outputs/
python3 src/build_xlsx.py         # regenerates outputs/ebola_timeseries.xlsx
```

## Methodology

The full methodology is in [METHODOLOGY.md](METHODOLOGY.md). Key rules:

- **Source preference order**: WHO AFRO Sitrep > WHO Disease Outbreak News > CDC > Africa CDC > established wires (Reuters, AP, AFP, BNO News). Within each tier, the most recent reconciled snapshot wins.
- **Lookback**: every run re-checks the most recent 7 rows against the latest sources and applies revisions in place. Every revision is logged in `data/notes.md`.
- **No-dip rule**: cumulative metrics are monotonically non-decreasing. A single source proposing a downward revision is held in NOTES; the dip is only applied when multiple high-value sources confirm. WHO Director-General statements count as a high-value source.
- **Provisional bars**: chart bars after the latest WHO Weekly Sitrep "as of" date are diagonally hatched to mark them as provisional.

## License

Data: CC-BY 4.0. Code: MIT. See `LICENSE-DATA` and `LICENSE-CODE`.

## About

Maintained by [Web Begole](https://www.linkedin.com/in/webbegole/). The methodology is intended to be reproducible: clone the repo, install the deps, and rebuild the charts from the CSVs.

Contact: [@web_begole](https://x.com/web_begole) on X · [linkedin.com/in/webbegole](https://www.linkedin.com/in/webbegole/)

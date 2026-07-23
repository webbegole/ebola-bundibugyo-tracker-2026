# Methodology

## What this is

A daily time series of the 2026 Ebola (Bundibugyo) outbreak, compiled from official public-health sources for academic use. Tracks the global outbreak total across all reporting countries (currently DRC and Uganda; designed to absorb additional countries as they emerge). Aggregate counts only. No individuals named. No medical advice.

## Data files

The CSVs, `story.md`, and `notes.md` in `data/` are the source of truth. The XLSX in `outputs/` is a convenience export; do not edit it.

- `data/timeseries.csv` — main daily series, global totals only. One row per Report Date. Includes `recovered_global` (cumulative recovered confirmed cases; see "Recovered and active cases"). See `README.md` for the schema.
- `data/country_breakdown.csv` — per-country detail in long format (DRC, Uganda, future reporters), including a per-country `recovered` column. Grows as new countries report cases.
- `data/declarations.csv` — per-country CDC advisory, CDC travel notice, and WHO declaration status with primary-source URLs. Schema: `country, first_report_date, case_status, cdc_advisory, cdc_url, cdc_travel_notice_level, cdc_travel_notice_url, who_status, who_url, notes`. The CDC fields cover two distinct advisory systems: HAN (clinician-facing alerts in `cdc_advisory`/`cdc_url`) and Travel Health Notices (traveler-facing per-country level in `cdc_travel_notice_level`/`cdc_travel_notice_url`, drawn from wwwnc.cdc.gov/travel/notices). Travel notice levels run 1 (Practice Usual Precautions) through 4 (Avoid All Travel). Updates when declarations change, a travel-notice level shifts, or a new country starts reporting cases.
- `data/story.md` — narrative summary. Markdown with two sections: "Story so far" (slow-moving context) and "Latest update" (the most recent material development, refreshed by the daily run when warranted). Rendered as the lead block on the site.
- `data/notes.md` — append-only methodology and revision log.

## Adding a new country

When a third country starts reporting cases:

1. Add the new country's cases to the running global totals in `timeseries.csv`. `total_global = suspected_global + confirmed_global`.
2. Add per-country rows for that date to `country_breakdown.csv` covering DRC, Uganda, and the new country. Use country-specific sources where available.
3. If the new country becomes operationally significant (sustained transmission, regular WHO reporting), consider adding a per-country breakout column on the main timeseries alongside Uganda's `uganda_confirmed` and `uganda_deaths`.
4. Add a row to `declarations.csv` if the country has its own CDC HAN, CDC Travel Health Notice, or WHO country-specific advisory for this outbreak (see "Adding a country to `declarations.csv`" below).
5. Log the scope change as a new bullet in `notes.md`.

## Adding a country to `declarations.csv`

`declarations.csv` is country × CDC HAN / CDC Travel Health Notice / WHO declaration, scoped to this outbreak. Add a row when **any one** of the following becomes true for a country:

- The country starts reporting confirmed or suspected cases (this also triggers timeseries.csv and country_breakdown.csv updates).
- CDC issues a country-specific Travel Health Notice for this outbreak at any level (1 through 4).
- CDC publishes a country-specific Health Alert Network notice for this outbreak, or a multi-country HAN explicitly names the country.
- WHO issues a country-specific declaration, statement, or DON entry beyond the joint PHEIC.
- A non-US national health authority (e.g., Public Health Agency of Canada, ECDC for individual EU members) issues its own outbreak-specific advisory for the country — *and* that advisory has a stable primary-source URL we can cite.

Do **not** add a row solely because the country appears in another country's advisory or entry restriction. Example: South Sudan is named in the US entry restrictions for non-US passport holders who travelled to DRC, Uganda, or South Sudan, but South Sudan has no CDC HAN, no CDC Travel Health Notice, and no WHO country-specific advisory for this outbreak as of the runs through 2026-05-31. Its inclusion in other countries' advisories is captured in the affected countries' `notes` fields, not as its own row.

Schema reminder: the columns are `country, first_report_date, case_status, cdc_advisory, cdc_url, cdc_travel_notice_level, cdc_travel_notice_url, who_status, who_url, notes`. There is no column for State Department travel advisories, non-US national advisories, Africa CDC PHECS, or other government measures; those live in the `notes` field. If a particular column becomes recurring enough to warrant structured cells (e.g., a `state_dept_advisory_level` column), extend the schema and migrate existing rows.

### Verification protocol on each daily run

When you mark "declarations.csv: no change" on a daily run, you must have actually **fetched the per-country CDC Travel Notice URL and verified the level on the page**, plus scanned the [CDC Travel Notices index](https://wwwnc.cdc.gov/travel/notices) for any new outbreak-related notices. A URL that resolves is not the same as the level being unchanged: CDC sometimes re-uses URLs from prior outbreaks (Uganda's `/level1/ebola-uganda` URL kept serving stale Sudan-virus content after CDC moved Uganda's BVD notice to `/level2/`). The lesson on 2026-05-31 (PM4): six consecutive daily runs recorded "no change" while CDC had in fact raised Uganda from Level 1 to Level 2 on May 27.

## Source preference order

Always prefer the most reconciled source available. In order:

1. WHO AFRO Weekly External Situation Report (gold standard, reconciled across DRC MoH and Uganda MoH).
2. WHO Disease Outbreak News (DON), which carries an explicit "as of" date.
3. CDC Situation Summary.
4. Africa CDC briefings.
5. BNO News, Reuters, AP, AFP. Daily wires, used only when nothing above is fresher.

The WHO Sitrep can revise numbers down as well as up. That's a feature of better data. Take the revision and log it (subject to the no-dip rule below).

## Daily task

1. Search for the latest numbers across the source preference order.
2. Append one row at the bottom of `timeseries.csv`. Fill all columns. `total_global = suspected_global + confirmed_global`.
3. Run the lookback (next section).
4. Append a NOTES bullet to `data/notes.md` for any revision or methodology decision made this run.
5. Regenerate the chart PNGs: `python3 src/generate_charts.py`.
6. Regenerate the XLSX export if needed: `python3 src/build_xlsx.py`.

## Backfilling missed days

The tracker targets **one row per calendar day**. A day can go un-rowed for two reasons: the scheduled run did not fire (machine offline, as on 2026-06-04 and 2026-06-06), or an earlier run folded the date into a later "catch-up" row. Both leave a calendar gap. On every run, close those gaps before appending today's row.

Procedure:

1. **Detect the gap.** Read the last Report Date in `timeseries.csv`. List every calendar date from that date+1 through today that has no row.
2. **Source each missing date.** For each gap date, pull that date's figure. The BNO `@BNOFeed` Daily Ebola Update graphic is published daily and is the primary backfill source (scroll the `@BNOFeed` timeline back to the dated graphic). Apply WHO/CDC-reconciled figures for any component where a reconciled "as of" value covers that date (e.g. a WHO DON dated on or after the gap date supersedes the BNO running count for the dates it reconciles).
3. **Insert in date order.** Add the row in its correct chronological position (the file stays sorted by date). Add matching per-country rows to `country_breakdown.csv`. This is the one sanctioned mid-history insertion; it is not a revision of any existing row.
4. **Flag it.** Prefix the row's `primary_source` with `BACKFILL (added YYYY-MM-DD run, daily-row policy):` and log a `notes.md` bullet naming the gap dates, the source per date, and the reason the gap existed.
5. **Respect the rules.** The no-dip rule and cumulative monotonicity apply across the now-denser series exactly as for appended rows. BVD-style instrument gaps (a WHO-reconciled day sitting between two higher BNO running-count days) stay monotonic and are noted, not smoothed.

A backfilled BNO row carries the same provisional status and downward-reconciliation risk as any same-day BNO row (the running count has overshot later WHO reconciliation by ~15-18%). When WHO later reconciles a backfilled date, apply the change under the normal lookback/no-dip path.

The fold convention (collapsing a multi-day gap into a single "as of" row) is retired for routine gaps in favour of one row per day. It may still be used when no daily source exists for the intermediate dates; record that choice in `notes.md`.

## Lookback

On every run, re-check the last 3 rows against the latest sources. When a higher-preference source publishes revised figures for a date already in the timeseries:

- Edit the row's numeric columns in place.
- Refresh `primary_source` and `source_timestamp` on the revised row.
- Append a dated bullet to `notes.md` naming the row, the fields changed, and the old → new values.

The 3-day window is calibrated to the actual revision pattern observed: BNO News figures get superseded by a WHO DON or Sitrep within 1 to 3 days, and the WHO Sitrep gives a single "as of" date data point rather than revising a multi-day window. A 7-day lookback was used at the start of the outbreak and was reduced to 3 days on 2026-05-27 after a week of observed revisions confirmed the tighter window is sufficient.

## No-dip rule (cumulative figures)

Cumulative metrics (`suspected_global`, `confirmed_global`, `total_global`, `suspected_deaths_global`) are monotonically non-decreasing on this tracker. When a source proposes a downward revision (a "dip"), the previous higher value is **carried forward** unless multiple independent high-value sources confirm the dip.

**High-value sources** for the purpose of this rule:

- WHO official publications (Weekly Sitrep, Disease Outbreak News).
- WHO Director-General statements at briefings, press conferences, or official remarks — these count as high-value even when not yet in a WHO publication. A DG-attributed figure carried by Reuters, AP, AFP, RFI, or a similar credentialed wire is acceptable.
- DRC Ministry of Health official press releases.
- Uganda Ministry of Health official press releases.
- CDC Situation Summary or HAN advisory.

A single high-value source proposing a dip is **not** enough. The classic case is a DRC MoH reclassification carried by one wire service. When that happens: hold the prior higher value in the row, log the dip claim in `notes.md` with the source attribution and the magnitude, and wait for WHO Sitrep / DON / DG remarks to confirm or refute.

**Upward revisions** follow normal source-preference rules. A single high-value source citing a higher figure is sufficient.

**When a dip is eventually accepted** (because a second high-value source corroborates): apply the dip with a NOTES bullet that names both corroborating sources and the date the rule's two-source threshold was met.

**MoH methodology-change carve-out.** When the downward revision is a formally-announced definitional cleanup by the official surveillance source (DRC MoH or Uganda MoH) — for example, removing suspected cases that subsequently tested negative after a lab capacity ramp-up, or zeroing a suspected-deaths column as part of the same cleanup — the two-source threshold is waived and the dip is applied with the MoH announcement as the sole high-value source. This is distinct from the standard no-dip case: it applies only when the MoH itself announces the methodology change (and the wire is faithfully carrying the announcement, not paraphrasing an unreconciled recount). The 2026-05-30 DRC MoH ~700-case removal (lab capacity ramp-up; remaining cases tested negative for Ebola) is the prototypical case. The exemption is recorded explicitly in `src/validate.py`'s `NO_DIP_EXEMPTIONS` dict (date → exempt columns) so the no-dip validator skips the named columns on that date. Every such exemption gets a NOTES bullet citing the MoH announcement and the figures applied.

**Rationale**: cumulative drops confuse a general-audience reader (the chart looks like deaths are coming back to life). In this outbreak's data environment, most apparent drops are definitional reclassifications, not actual recoveries. The no-dip rule biases toward the higher figure until the lower one earns multi-source backing. The MoH carve-out exists because a definitional cleanup announced by the surveillance authority *is* the reclassification — by definition — and waiting for WHO reconciliation in that case is a delay, not a correction.

## Rules

- Append new dates at the bottom of `timeseries.csv`. The file is kept in chronological order. Mid-history **insertion is allowed only to backfill a missed calendar date** under the "Backfilling missed days" policy below; you still never re-sequence or rewrite an existing row outside the lookback policy.
- Existing rows only change under the lookback policy. Every change goes in `notes.md`.
- If no new numbers and no revisions, skip the day.
- Always cumulative, never daily increments. The deltas are derived by `generate_charts.py`.
- If a source gives a combined total without splitting suspected vs. confirmed, put it in `total_global` and leave `suspected_global` and `confirmed_global` blank, with a note in `primary_source`.

## Sources

| Source | URL | Cadence |
|---|---|---|
| WHO AFRO Weekly Sitrep | https://www.afro.who.int/countries/democratic-republic-of-congo/publications | Weekly |
| WHO Disease Outbreak News | https://www.who.int/emergencies/disease-outbreak-news | Periodic, "as of" dated |
| WHO outbreak page | https://www.who.int/emergencies/situations/ebola-outbreak---drc-2026 | Periodic |
| CDC Situation Summary | https://www.cdc.gov/ebola/situation-summary/ | Every 1 to 2 days |
| Africa CDC | https://africacdc.org | Periodic |
| ECDC | https://www.ecdc.europa.eu/en/ebola-virus-disease-outbreak-democratic-republic-congo-and-uganda | Weekly |
| BNO News | https://bnonews.com | Daily |
| Reuters | https://www.reuters.com | As events occur |
| Wikipedia | https://en.wikipedia.org/wiki/2026_Ituri_Province_Ebola_epidemic | Ongoing |

### Real-time signal (X / Twitter)

Useful as a leading indicator for figures that haven't hit the wire yet (DRC MoH press statements, Uganda MoH press releases, WHO Director-General quotes from briefings).

Search URL pattern: `https://x.com/search?q=ebola%20outbreak&src=typed_query&f=live`

Use the Claude in Chrome MCP against Web's signed-in browser; x.com search results are gated for unauthenticated viewers and the xcancel mirror has been intermittently blocked by anti-bot challenges. The page is client-rendered, so plain `curl`/`requests` returns a shell — use `mcp__Claude_in_Chrome__navigate` + `get_page_text` (see SKILL.md "Unattended-run handling for Chrome MCP" for the browser-selection flow).

**Filtering rules (strict)**: trust only primary public-health institutions, established wire services, and credentialed health journalists. Examples of trustworthy accounts: @WHO, @WHOAFRO, @DrTedros, @AfricaCDC, @CDCgov, @MinSanteRDC, @MinofHealthUG, @Reuters, @AP, @AFP, @BNODesk, @BNONews, @CIDRAP, @HelenBranswell, @KrutikaKuppalli, @MackayIM, @TulioDeOliveira. Ignore anonymous accounts, opinion-only accounts, conspiracy/anti-vax/pandemic-skeptic accounts, influencers, engagement-farming threads. A tweet from a credentialed source is a lead, not a citation: before logging a figure, follow the tweet's link or wait for the corresponding statement to appear on the institutional channel and cite that.

## Charts

Four PNGs are produced on every run, written to `outputs/`:

1. `YYYY-MM-DD_ebola-cases-7d-rolling-sum.png` — stacked bars of suspected (bottom) and laboratory-confirmed (top) new cases summed over the trailing 7 days. Two cumulative lines on the right axis: cumulative TOTAL cases (bronze) and cumulative LAB-CONFIRMED cases (deep red). The gap between the two lines is the share of the running count still in clinical-suspicion-only status.
2. `YYYY-MM-DD_ebola-deaths-7d-rolling-sum.png` — bars of suspected deaths summed over the trailing 7 days, with cumulative suspected deaths on the right axis.
3. `YYYY-MM-DD_ebola-active-cases.png` — active ("live") cases. Daily bars: new confirmed cases drawn upward (inflow), new recoveries and new confirmed deaths drawn downward and stacked (outflow). Right-axis line: cumulative active cases = cumulative confirmed − cumulative recovered − cumulative confirmed deaths. When the downward bars exceed the upward bar on a day, the active line falls (the outbreak is resolving faster than it grows). See "Recovered and active cases" below.
4. `YYYY-MM-DD_ebola-active-wow.png` — week-over-week percent change in active cases. For each date, the mean active level over the trailing 7 days (t-6..t) is compared to the mean over the immediately prior 7 days (t-13..t-7); the point is `(current_mean / prior_mean − 1) × 100`. Two adjacent 7-day averaging windows smooth the daily spikes so the line reads as a growth-rate trend: above zero the active pool is still expanding week-over-week, below zero it is contracting. Undefined until 14 days of active-case history exist, and skipped on any date where the prior-window mean is non-positive. Implemented as `compute_active_wow` + `render_active_wow_chart` in `src/generate_charts.py`. Rendered on a **symlog** y-axis (linear within ±10%, logarithmic beyond) so the line stays readable across the +200%-to-single-digits range and still plots the day the rate crosses below zero (active pool shrinking). Gridlines are fixed at 0, 10, 20, 30, 50, 100, and 200 percent (mirrored negative).

The `YYYY-MM-DD` prefix is the most recent Report Date in `timeseries.csv`.

A doubling-time chart is also implemented (`render_doubling_time_chart` in `src/generate_charts.py`) but is **not currently rendered**. Early confirmed-case figures in this outbreak are heavily revised by WHO Sitrep reconciliation, which makes the trailing-window exponential fit move in ways that misrepresent the underlying transmission dynamics. The chart will be re-enabled once the data stabilizes — likely after two or three WHO Weekly Sitreps have published and the early-data reconciliation cycle has settled. The design and methodology of the chart are documented in the "Doubling-time chart (v1 scaffold)" subsection below.

### Rolling-sum methodology

Baseline: 2026-05-14 (the day before outbreak declaration) is treated as zero across all metrics. The May 15 row's daily delta therefore equals the full cumulative count on declaration day. While the trailing window is shorter than 7 days (May 15 through May 20), the rolling sum equals total outbreak-to-date growth. From May 21 onward every bar is a true 7-day window.

The rolling sum can in principle go negative when underlying daily deltas include a downward revision. After the no-dip rule was adopted on 2026-05-25 this is much less common, but the chart will still draw a bar below zero if it happens.

### Provisional vs. Sitrep-stable bars

Bars on each chart are marked as either solid (Sitrep-stable) or diagonally hatched (provisional, subject to revision). The boundary is the constant `LAST_SITREP_STABLE_DATE` near the top of `src/generate_charts.py`. A row's Report Date later than this value is treated as provisional.

Update this constant when a new WHO Weekly Sitrep lands. Set it to the new Sitrep's "as of" date and re-run the script. The hatching boundary will shift forward and any newly-stable rows will switch to solid bars.

### Revision-range footnote

The caption under each chart cites two observed ranges, one for upward revisions and one for downward revisions, kept in `OBSERVED_UPWARD_REVISION_RANGE` and `OBSERVED_DOWNWARD_REVISION_RANGE` near the top of `src/generate_charts.py`. After applying lookback revisions, scan `notes.md` for the actual percent change on each revised row. If the running history drifts outside the cited range on either side, update the matching constant.

Calculation: for each revision logged in NOTES, compute `(new − old) / old × 100`. The range in the footnote should bracket the observed values with a small margin.

Upward revisions are the WHO Sitrep / DON reconciliation pattern (same-day wire counts undercount; WHO catches up). Downward revisions are the MoH methodology-change carve-out (DRC MoH cleaned baseline on 2026-05-30, zeroing the suspected-deaths column and removing test-negative cases). The two directions are tracked separately because they reflect different mechanisms.

### Recovered and active cases

`recovered_global` in `timeseries.csv` and `recovered` in `country_breakdown.csv` track cumulative recovered/discharged **confirmed** cases. The source is the BNO `@BNOFeed` Daily Ebola Update graphic, which reports Confirmed / Recovered / Deaths per country and a global total; the graphic's own totals and the tracker's other citations are used to fill the column. Recovered figures are transcribed the same way case and death figures are.

Basis and definition. BNO reports recovered and deaths against **confirmed** cases, so the active ("live") case count is confirmed-basis: `active = confirmed_global − recovered_global − confirmed_deaths_global`. Suspected cases are excluded (there is no recovered/deaths breakdown for suspected). Active is a derived quantity, computed in `generate_charts.py`, not stored in the CSV.

Monotonicity. Cumulative recovered is monotonically non-decreasing and is covered by the no-dip rule in `validate.py` exactly like the other cumulative columns. Active cases are *not* monotonic by design — the whole point of the chart is that active can fall.

Gaps and forward-fill. Recovered is left **blank** on any date where no source published a figure (a BNO publication gap, or a WHO/wire day that gave cases and deaths but not recovered). Blanks are not guessed or interpolated in the CSV. For the active-case chart only, `generate_charts.py` forward-fills cumulative recovered (carries the last known value) so the active line stays defined; on a forward-filled day the recovery outflow reads as zero and the accumulated recoveries land as a catch-up bar on the next day a figure was published. The validator's latest-date country-sum cross-check for recovered is skipped on any day a country's recovered cell is blank.

Early baseline. BNO began carrying a Recovered figure on 2026-06-03 (DRC 6). Earlier dates (2026-05-15 through 2026-06-02) are treated as recovered = 0, consistent with the outbreak's 2026-05-14 zero baseline: recoveries in the first weeks of a high-CFR Bundibugyo outbreak were effectively nil, and no source reported otherwise. This is a documented baseline assumption, not a sourced figure.

Backfill provenance. The recovered series was backfilled on 2026-07-23 from (a) per-country recovered figures already transcribed into `country_breakdown.csv` and `timeseries.csv` primary_source citations across the run history, (b) the BNO `@BNOFeed` daily graphics read via Chrome, and (c) the France rule (0 until the single imported case was discharged on 2026-07-04, then 1). BNO began carrying a Recovered column on its 2026-06-04 graphic; the 2026-06-03 graphic has no Recovered column, so 06-03's value (8) is reconstructed from the 06-04 graphic's delta rather than read directly. In a second pass the same day, the full June series was re-read against the embedded-date BNO graphics: this corrected 06-06 (which had been holding 06-07's figures) and hard-filled 06-05, 06-07, 06-21, and 06-22 from their graphics. Residual blank dates: 2026-06-14 and 2026-07-15 through 07-18. 06-14 is a BNO anomaly, not a missing graphic: the 14 June graphic reported total recovered 61 (DR Congo 56, +21), which the 15 June graphic then contradicted at 53 (DR Congo 48). Recoveries cannot reverse, so the 06-14 over-count is treated as a BNO reporting error and left blank rather than encoded as a monotonicity-breaking spike. 07-15 through 07-18 fall in a BNO publication gap (no daily graphic exists). Both ranges forward-fill in the chart and can be hard-filled later if a WHO Sitrep reconciles recovered.

### Doubling-time chart (v1 scaffold)

The doubling-time chart fits `log(cumulative confirmed cases) = a + b·t` over the trailing 7 days using closed-form OLS, then reports `T_d = ln(2) / b` per day. Windows with zero or non-positive growth are dropped.

Reference lines: 2-day doubling (lower bound of fast spread) and 7-day doubling (threshold below which an outbreak is in exponential acceleration; only drawn when the y-axis range includes it).

Constants in `src/generate_charts.py`:
- `DOUBLING_WINDOW` (default 7) — trailing days used to fit the exponential.
- `DOUBLING_FLOOR` (0.5d) and `DOUBLING_CEIL` (60d) — display clipping.

Limitations to note when reading the chart:
- Doubling time of a cumulative count, not a daily incidence count.
- Sensitive to revisions and source switches.
- Not the same as R(t). R(t) needs a serial-interval distribution and at least one full generation interval of data (~9-15 days for Bundibugyo). Plan to add R(t) once we have ~20-25 days of clean incidence.

## End condition

When WHO or DRC declares the event over, add a final row with terminal counts, note the declaration in `primary_source`, and stop. Leave the repo standing as a historical reference.

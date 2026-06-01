"""
Generate editorial-style PNG charts from the tracker CSVs.

Reads data/timeseries.csv, computes day-over-day deltas with a 2026-05-14=0
baseline, and renders three charts as PNG files in outputs/:
  - cases (stacked bars + two cumulative lines)
  - deaths (bars + cumulative line)
  - doubling-time (line scaffold)

Output filenames follow the YYYY-MM-DD_short-descriptive-name.png convention
and use the most recent Report Date as the date prefix.

Usage:
    python3 src/generate_charts.py
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib import rcParams
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# --- Paths -------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
TIMESERIES_CSV = DATA_DIR / "timeseries.csv"

# --- Attribution -------------------------------------------------------------
# Byline rendered at the bottom of every chart, above the source citation.
BYLINE = "Tracker: Web Begole · @web_begole · linkedin.com/in/webbegole"

# --- Provisional-data boundary -----------------------------------------------
# Anything on this date or earlier is considered "Sitrep-stable" (covered by a
# WHO Weekly External Situation Report and unlikely to be revised by more than
# a few percent). Dates after this are provisional — recent wire reports often
# get revised upward when WHO DON or the next Sitrep publishes.
#
# Update this when a new WHO Weekly Sitrep lands. Set to the Sitrep's "as of"
# date. Format: "YYYY-MM-DD".
LAST_SITREP_STABLE_DATE = "2026-05-24"

# Observed magnitude of revisions, split by direction. Upward revisions come
# from WHO Sitrep / DON reconciliation when same-day wire counts undercount.
# Downward revisions come from the MoH methodology-change carve-out
# (METHODOLOGY.md): DRC MoH or Uganda MoH formally announce a definitional
# cleanup such as removing suspected cases that tested negative for Ebola.
# The two directions reflect different mechanisms so they're tracked separately.
#
# Update either constant when the running revision history in `data/notes.md`
# drifts outside its range. Compute (new - old) / old * 100 for each revision.
#
# Upward history (as of 2026-05-31): May 18 sus +33.7%, May 18 deaths +24.5%,
# May 21 sus +11.2%, May 21 conf +32.8%, May 21 deaths +6.0%, May 24 sus +4.3%,
# May 24 conf +16.1%, May 25 conf +12.5%, May 25 sus +0.22%, May 25 total +0.59%.
#
# Downward history (as of 2026-05-31): 2026-05-30 DRC MoH methodology cleanup
# applied to May 30 row — sus -61.5%, total -43.9%, sus_deaths -100% (column
# zeroed when DRC MoH reclassified suspected deaths as non-Ebola). Same dip
# carried into May 31 row (relative to the WHO DON605 baseline) — sus -50.7%,
# total -34.5%, sus_deaths -100%.
OBSERVED_UPWARD_REVISION_RANGE = "<1-35%"
OBSERVED_DOWNWARD_REVISION_RANGE = "up to 100%"

# Baseline-reset dates. When the official surveillance source (DRC MoH or
# Uganda MoH) formally re-baselines the series via the MoH methodology-change
# carve-out (METHODOLOGY.md), the row's cumulative values are a NEW starting
# point — not a delta against the prior row's pre-cleanup baseline. Computing
# `cum[i] - cum[i-1]` across that boundary produces a spurious negative delta
# that would render as a negative bar on the rolling-sum chart.
#
# For each date listed here, the daily delta is forced to zero (the cleaned
# baseline is the floor, not a downward delta). Cumulative lines still use
# the row's actual cumulative value, so the drop is visible on the line but
# the bars stay non-negative. The cumulative-line callout in render_cases_chart
# annotates the reset visually so a viewer understands the drop is a cleanup,
# not a reversal.
#
# Update this set when a new MoH cleanup is applied and a NO_DIP_EXEMPTIONS
# entry is added in src/validate.py.
BASELINE_RESET_DATES = {
    "2026-05-30",  # DRC MoH ~700-case removal; lab capacity ramp-up cleanup.
}
# -----------------------------------------------------------------------------

# --- Style -------------------------------------------------------------------
# Editorial / news-graphic conventions: restrained palette, sans-serif,
# minimal chartjunk, data labels on bars, source caption at the bottom.

COLOR_SUSPECTED = "#4A6FA5"        # muted slate blue
COLOR_CONFIRMED = "#C24E4E"        # warm accent for the smaller, more certain stack
COLOR_DEATHS = "#2C3E50"           # dark neutral
COLOR_CUMULATIVE = "#8B5A2B"       # sienna/bronze — cumulative total running line
COLOR_CUMULATIVE_CONF = "#7A2C2C"  # deeper red — cumulative lab-confirmed line
COLOR_DOUBLING = "#2D5F5D"         # dark teal — doubling-time line (separate metric)
COLOR_AXIS = "#444444"
COLOR_GRID = "#DDDDDD"
COLOR_TEXT = "#222222"
COLOR_SUBTLE = "#666666"

rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 15,
    "axes.edgecolor": COLOR_AXIS,
    "axes.labelcolor": COLOR_TEXT,
    "axes.titlecolor": COLOR_TEXT,
    "axes.titlesize": 20,
    "axes.titleweight": "bold",
    "axes.labelsize": 16,
    "xtick.labelsize": 15,
    "ytick.labelsize": 15,
    "xtick.color": COLOR_AXIS,
    "ytick.color": COLOR_AXIS,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": COLOR_GRID,
    "grid.linewidth": 0.7,
    "axes.axisbelow": True,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


# --- Data loading ------------------------------------------------------------

def load_data(csv_path: Path):
    """Load timeseries.csv and compute daily deltas + 7-day rolling sums.

    Returns a list of per-row dicts with keys: date, d_sus, d_conf, d_deaths,
    d_conf_deaths, cum_sus, cum_conf, cum_total_cases, cum_deaths,
    cum_conf_deaths, cum_total_deaths, r7_sus, r7_conf, r7_deaths,
    r7_conf_deaths, window_size.
    """
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            date = r["report_date"]
            if not date or not date.startswith("2026-"):
                continue
            rows.append({
                "date": date,
                "sus": int(r["suspected_global"]) if r["suspected_global"] else 0,
                "conf": int(r["confirmed_global"]) if r["confirmed_global"] else 0,
                "deaths": int(r["suspected_deaths_global"]) if r["suspected_deaths_global"] else 0,
                "conf_deaths": int(r["confirmed_deaths_global"]) if r["confirmed_deaths_global"] else 0,
            })

    # Baseline: May 14 = 0 across all metrics, so the first row's delta equals
    # its cumulative value.
    #
    # Reset-day handling: on a date in BASELINE_RESET_DATES the row's cumulative
    # values are a NEW baseline produced by a MoH methodology cleanup, not a
    # delta against the prior row. Computing cum[i] - cum[i-1] across the
    # reset boundary would give a spurious negative daily delta and a negative
    # bar on the rolling-sum chart. We force the daily delta to zero on the
    # reset day; the cleaned baseline becomes prev for the next iteration so
    # subsequent days compute normal positive deltas against it.
    baseline = {"sus": 0, "conf": 0, "deaths": 0, "conf_deaths": 0}
    deltas = []
    prev = baseline
    for cur in rows:
        is_reset = cur["date"] in BASELINE_RESET_DATES
        deltas.append({
            "date": cur["date"],
            "d_sus": 0 if is_reset else cur["sus"] - prev["sus"],
            "d_conf": 0 if is_reset else cur["conf"] - prev["conf"],
            "d_deaths": 0 if is_reset else cur["deaths"] - prev["deaths"],
            "d_conf_deaths": 0 if is_reset else cur["conf_deaths"] - prev["conf_deaths"],
            "is_reset": is_reset,
            # Carry the cumulative running totals through so the renderers can
            # plot a secondary "cumulative outbreak total" line alongside the
            # 7-day rolling bars.
            "cum_sus": cur["sus"],
            "cum_conf": cur["conf"],
            "cum_total_cases": cur["sus"] + cur["conf"],
            "cum_deaths": cur["deaths"],
            "cum_conf_deaths": cur["conf_deaths"],
            "cum_total_deaths": cur["deaths"] + cur["conf_deaths"],
        })
        prev = cur

    # Trailing 7-day rolling sum of the deltas.
    for i, row in enumerate(deltas):
        window = deltas[max(0, i - 6): i + 1]
        row["r7_sus"] = sum(w["d_sus"] for w in window)
        row["r7_conf"] = sum(w["d_conf"] for w in window)
        row["r7_deaths"] = sum(w["d_deaths"] for w in window)
        row["r7_conf_deaths"] = sum(w["d_conf_deaths"] for w in window)
        row["window_size"] = len(window)

    return deltas


# --- Rendering ---------------------------------------------------------------

def annotate_bars(ax, xs, values, offset_above=None, fontsize=15, fontweight="bold"):
    """Place a numeric label above each positive bar and below each negative bar."""
    if not values:
        return
    yspan = max(abs(min(values)), abs(max(values)), 1)
    pad = yspan * 0.015
    for x, v in zip(xs, values):
        if v == 0:
            continue
        if v > 0:
            ax.text(x, v + pad, f"{v:+,}", ha="center", va="bottom",
                    fontsize=fontsize, fontweight=fontweight, color=COLOR_TEXT)
        else:
            ax.text(x, v - pad, f"{v:+,}", ha="center", va="top",
                    fontsize=fontsize, fontweight=fontweight, color=COLOR_TEXT)


def annotate_stacked_totals(ax, xs, suspected, confirmed, fontsize=15):
    """For the cases chart, show the stack TOTAL above the top of each column."""
    totals = [s + c for s, c in zip(suspected, confirmed)]
    if not totals:
        return
    yspan = max(abs(min(totals)), abs(max(totals)), 1)
    pad = yspan * 0.02
    for x, t in zip(xs, totals):
        if t == 0:
            continue
        if t > 0:
            ax.text(x, t + pad, f"{t:+,}", ha="center", va="bottom",
                    fontsize=fontsize, fontweight="bold", color=COLOR_TEXT)
        else:
            ax.text(x, t - pad, f"{t:+,}", ha="center", va="top",
                    fontsize=fontsize, fontweight="bold", color=COLOR_TEXT)


DEFAULT_CUMULATIVE_MARKERSIZE = 5.5
DEFAULT_CUMULATIVE_LINEWIDTH = 1.6


def mark_baseline_resets(ax, dates, label_text="MoH baseline reset"):
    """Draw a thin vertical line at each baseline-reset date and label it.

    The label sits at the top of the axis so it doesn't compete with the
    bars. Use a muted gray so the marker reads as chart furniture, not data.
    """
    for i, d in enumerate(dates):
        if d not in BASELINE_RESET_DATES:
            continue
        ax.axvline(i, color=COLOR_SUBTLE, linewidth=1.0,
                   linestyle=(0, (4, 3)), zorder=1, alpha=0.7)
        ymin, ymax = ax.get_ylim()
        y = ymax - (ymax - ymin) * 0.045
        ax.text(i + 0.15, y, label_text,
                fontsize=11, color=COLOR_SUBTLE, style="italic",
                ha="left", va="top", zorder=6)


def overlay_cumulative_line(ax, xs, series, axis_label, axis_color=None):
    """Add a secondary y-axis with one or more lines tracing cumulative
    running totals.

    `series` is a list of tuples. Each tuple is either `(values, color)`
    (uses defaults) or `(values, color, style)` where `style` is a dict
    with optional keys: `markersize`, `linewidth`, `marker`. This is how
    we visually differentiate co-plotted lines (e.g., bigger markers on
    the secondary series so it reads distinctly against the primary).

    The highest-magnitude series governs the right-axis scale. `axis_color`
    controls tick/spine color; defaults to the first series's color so the
    axis visually anchors to the headline line.

    This is the chart's odometer reading: bar height encodes 7-day velocity,
    overlay lines encode running totals at each date so the viewer can read
    both quantities without conflating them. No per-point labels are drawn.

    Returns the twin axis so the caller can attach it to the legend.
    """
    ax2 = ax.twinx()
    primary_color = axis_color if axis_color else series[0][1]

    # Plot each series — first one drawn last (on top) for visual priority.
    for entry in reversed(series):
        if len(entry) == 2:
            values, color = entry
            style = {}
        else:
            values, color, style = entry
        markersize = style.get("markersize", DEFAULT_CUMULATIVE_MARKERSIZE)
        linewidth = style.get("linewidth", DEFAULT_CUMULATIVE_LINEWIDTH)
        marker = style.get("marker", "o")
        ax2.plot(xs, values, color=color, linewidth=linewidth,
                 marker=marker, markersize=markersize, markerfacecolor=color,
                 markeredgecolor="white", markeredgewidth=0.9, zorder=5)

    # Y-axis formatting: match primary axis (no decimals, comma separators).
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax2.tick_params(axis="y", colors=primary_color, labelsize=13)
    ax2.set_ylabel(axis_label, color=primary_color, labelpad=12, fontsize=14)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_color(primary_color)
    ax2.grid(False)

    # Top margin: match the primary axis's 1.35x headroom so the cumulative line
    # never encroaches on the upper-left legend block. Bottom margin: small
    # negative pad below the minimum so markers near zero don't graze the
    # baseline frame. Scale is set by the highest-magnitude series.
    all_values = [v for entry in series for v in entry[0]]
    if all_values:
        ymax = max(all_values)
        ymin = min(min(all_values), 0)
        yspan = (ymax - ymin) if (ymax - ymin) > 0 else max(ymax, 1)
        top = (ymax * 1.35) if ymax > 0 else 1
        bottom = ymin - yspan * 0.05
        ax2.set_ylim(bottom, top)

    return ax2


def render_cases_chart(deltas, out_path: Path):
    dates = [d["date"] for d in deltas]
    short_dates = [d[5:] for d in dates]  # MM-DD
    sus = [d["r7_sus"] for d in deltas]
    conf = [d["r7_conf"] for d in deltas]
    cumulative_total = [d["cum_total_cases"] for d in deltas]
    cumulative_conf = [d["cum_conf"] for d in deltas]
    provisional = [d > LAST_SITREP_STABLE_DATE for d in dates]
    hatches = ["////" if p else "" for p in provisional]

    fig, ax = plt.subplots(figsize=(16, 9), dpi=100)
    xs = list(range(len(dates)))

    # Stacked bars: confirmed on bottom (more certain figure as the base),
    # suspected on top. Hatched on provisional dates.
    ax.bar(xs, conf, color=COLOR_CONFIRMED, width=0.68,
           label="Confirmed cases", edgecolor="white", linewidth=0.8,
           hatch=hatches)
    ax.bar(xs, sus, bottom=conf, color=COLOR_SUSPECTED, width=0.68,
           label="Suspected cases", edgecolor="white", linewidth=0.8,
           hatch=hatches)

    # Headroom above the tallest stacked bar so the legend (anchored
    # upper-left) doesn't collide with the data.
    stacked_tops = [s + c for s, c in zip(sus, conf)]
    if stacked_tops:
        bar_max = max(stacked_tops)
        if bar_max > 0:
            ax.set_ylim(top=bar_max * 1.35)

    # Overlay: two cumulative lines on the secondary axis. The bronze line
    # is cumulative TOTAL cases (suspected + confirmed). The deeper-red line
    # is cumulative LAB-CONFIRMED cases. The gap between them is the share
    # of the running count that is still clinical-suspicion-only. The
    # confirmed line gets a larger marker so the two are easy to tell apart
    # — they're warm-toned colors and could otherwise read as one series.
    ax2 = overlay_cumulative_line(
        ax, xs,
        series=[
            (cumulative_total, COLOR_CUMULATIVE),
            (cumulative_conf, COLOR_CUMULATIVE_CONF,
             {"markersize": 9.5, "linewidth": 2.0}),
        ],
        axis_label="Cumulative cases (global)",
        axis_color=COLOR_CUMULATIVE,
    )

    # Mark any MoH baseline-reset dates so the cumulative-line drop reads as
    # a documented methodology cleanup, not as the outbreak reversing.
    mark_baseline_resets(ax, dates)

    # Build a custom legend with Patch proxies so the hatched swatch renders.
    legend_handles = [
        Patch(facecolor=COLOR_CONFIRMED, edgecolor="white", label="Confirmed cases (7-day, left axis)"),
        Patch(facecolor=COLOR_SUSPECTED, edgecolor="white", label="Suspected cases (7-day, left axis)"),
    ]
    if any(provisional):
        legend_handles.append(
            Patch(facecolor="white", edgecolor=COLOR_AXIS, hatch="////",
                  label="Provisional (subject to revision)")
        )
    legend_handles.append(
        Line2D([0], [0], color=COLOR_CUMULATIVE, linewidth=1.8,
               marker="o", markersize=6, markerfacecolor=COLOR_CUMULATIVE,
               markeredgecolor="white",
               label="Cumulative total cases (right axis)")
    )
    legend_handles.append(
        Line2D([0], [0], color=COLOR_CUMULATIVE_CONF, linewidth=2.2,
               marker="o", markersize=10, markerfacecolor=COLOR_CUMULATIVE_CONF,
               markeredgecolor="white",
               label="Cumulative lab-confirmed cases (right axis)")
    )

    ax.set_xticks(xs)
    ax.set_xticklabels(short_dates)
    ax.set_xlabel("Report date (2026)", labelpad=12)
    ax.set_ylabel("Cases reported in the previous 7 days", labelpad=12)

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.grid(axis="x", visible=False)
    ax.axhline(0, color=COLOR_AXIS, linewidth=0.8)

    fig.suptitle("Ebola (Bundibugyo): 7-day rolling sum of new cases",
                 fontsize=26, fontweight="bold", color=COLOR_TEXT, x=0.07, ha="left", y=0.96)
    ax.set_title("Bars: new cases in the trailing 7 days. Line: cumulative outbreak total at each date.",
                 fontsize=17, fontweight="normal", color=COLOR_SUBTLE,
                 loc="left", pad=16)

    leg = ax.legend(handles=legend_handles, loc="upper left", frameon=False,
                    fontsize=13, handlelength=1.8, handleheight=1.2, ncol=3)
    for txt in leg.get_texts():
        txt.set_color(COLOR_TEXT)

    fig.text(0.07, 0.09, BYLINE, fontsize=12, color=COLOR_SUBTLE)
    fig.text(0.07, 0.055,
             "Source: WHO AFRO Weekly Sitrep, WHO Disease Outbreak News, "
             "CDC Situation Summary, Africa CDC, BNO News.",
             fontsize=12, color=COLOR_SUBTLE)
    fig.text(0.07, 0.02,
             f"Bars after {LAST_SITREP_STABLE_DATE} are provisional; revisions have run "
             f"+{OBSERVED_UPWARD_REVISION_RANGE} (Sitrep reconciliation) and "
             f"{OBSERVED_DOWNWARD_REVISION_RANGE} downward (MoH definitional cleanups).",
             fontsize=12, color=COLOR_SUBTLE, style="italic")

    fig.subplots_adjust(left=0.08, right=0.92, top=0.80, bottom=0.20)
    fig.savefig(out_path, dpi=100, facecolor="white")
    plt.close(fig)


def render_deaths_chart(deltas, out_path: Path):
    """Deaths chart, structurally identical to the cases chart.

    Stacked bars: confirmed deaths (bottom, the lab-attributed certain layer)
    + suspected deaths (top, clinical-suspicion-only). Hatched on provisional
    dates. Two cumulative lines on the right axis: total deaths (bronze) and
    confirmed deaths (deep red). The gap between the two lines is the share
    of the running death count still in clinical-suspicion-only status.

    The original deaths chart only showed suspected deaths. After DRC MoH
    zeroed the suspected-deaths column in the 2026-05-30 cleanup, "suspected
    deaths" stopped being a useful headline metric: real deaths are still
    accumulating, just on the confirmed side. Mirroring the cases chart's
    structure puts both layers on screen and keeps the death story honest.
    """
    dates = [d["date"] for d in deltas]
    short_dates = [d[5:] for d in dates]
    sus_deaths = [d["r7_deaths"] for d in deltas]
    conf_deaths = [d["r7_conf_deaths"] for d in deltas]
    cumulative_total_deaths = [d["cum_total_deaths"] for d in deltas]
    cumulative_conf_deaths = [d["cum_conf_deaths"] for d in deltas]
    provisional = [d > LAST_SITREP_STABLE_DATE for d in dates]
    hatches = ["////" if p else "" for p in provisional]

    fig, ax = plt.subplots(figsize=(16, 9), dpi=100)
    xs = list(range(len(dates)))

    # Stacked bars: confirmed deaths on bottom (the certain layer), suspected
    # deaths on top. Mirrors the cases chart's confirmed-cases-on-bottom
    # convention so a viewer can read both charts the same way.
    ax.bar(xs, conf_deaths, color=COLOR_CONFIRMED, width=0.68,
           label="Confirmed deaths", edgecolor="white", linewidth=0.8,
           hatch=hatches)
    ax.bar(xs, sus_deaths, bottom=conf_deaths, color=COLOR_SUSPECTED,
           width=0.68, label="Suspected deaths", edgecolor="white",
           linewidth=0.8, hatch=hatches)

    # Headroom above the tallest stacked bar so the legend (anchored
    # upper-left) doesn't collide with the data.
    stacked_tops = [s + c for s, c in zip(sus_deaths, conf_deaths)]
    if stacked_tops:
        bar_max = max(stacked_tops)
        if bar_max > 0:
            ax.set_ylim(top=bar_max * 1.35)

    # Overlay: two cumulative lines on the secondary axis. The bronze line
    # is cumulative TOTAL deaths (suspected + confirmed). The deeper-red line
    # is cumulative LAB-CONFIRMED deaths. The gap between them is the share
    # of the running death count still in clinical-suspicion-only status.
    ax2 = overlay_cumulative_line(
        ax, xs,
        series=[
            (cumulative_total_deaths, COLOR_CUMULATIVE),
            (cumulative_conf_deaths, COLOR_CUMULATIVE_CONF,
             {"markersize": 9.5, "linewidth": 2.0}),
        ],
        axis_label="Cumulative deaths (global)",
        axis_color=COLOR_CUMULATIVE,
    )

    # Mark any MoH baseline-reset dates so the cumulative-line drop reads as
    # a documented methodology cleanup, not as the outbreak reversing.
    mark_baseline_resets(ax, dates)

    # Build a custom legend with Patch proxies so the hatched swatch renders.
    legend_handles = [
        Patch(facecolor=COLOR_CONFIRMED, edgecolor="white", label="Confirmed deaths (7-day, left axis)"),
        Patch(facecolor=COLOR_SUSPECTED, edgecolor="white", label="Suspected deaths (7-day, left axis)"),
    ]
    if any(provisional):
        legend_handles.append(
            Patch(facecolor="white", edgecolor=COLOR_AXIS, hatch="////",
                  label="Provisional (subject to revision)")
        )
    legend_handles.append(
        Line2D([0], [0], color=COLOR_CUMULATIVE, linewidth=1.8,
               marker="o", markersize=6, markerfacecolor=COLOR_CUMULATIVE,
               markeredgecolor="white",
               label="Cumulative total deaths (right axis)")
    )
    legend_handles.append(
        Line2D([0], [0], color=COLOR_CUMULATIVE_CONF, linewidth=2.2,
               marker="o", markersize=10, markerfacecolor=COLOR_CUMULATIVE_CONF,
               markeredgecolor="white",
               label="Cumulative lab-confirmed deaths (right axis)")
    )
    leg = ax.legend(handles=legend_handles, loc="upper left", frameon=False,
                    fontsize=13, handlelength=1.8, handleheight=1.2, ncol=3)
    for txt in leg.get_texts():
        txt.set_color(COLOR_TEXT)

    ax.set_xticks(xs)
    ax.set_xticklabels(short_dates)
    ax.set_xlabel("Report date (2026)", labelpad=12)
    ax.set_ylabel("Deaths reported in the previous 7 days", labelpad=12)

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.grid(axis="x", visible=False)
    ax.axhline(0, color=COLOR_AXIS, linewidth=0.8)

    fig.suptitle("Ebola (Bundibugyo): 7-day rolling sum of new deaths",
                 fontsize=26, fontweight="bold", color=COLOR_TEXT, x=0.07, ha="left", y=0.96)
    ax.set_title("Bars: new deaths in the trailing 7 days. Lines: cumulative outbreak deaths at each date.",
                 fontsize=17, fontweight="normal", color=COLOR_SUBTLE,
                 loc="left", pad=16)

    fig.text(0.07, 0.09, BYLINE, fontsize=12, color=COLOR_SUBTLE)
    fig.text(0.07, 0.055,
             "Source: WHO AFRO Weekly Sitrep, WHO Disease Outbreak News, "
             "CDC Situation Summary, Africa CDC, BNO News.",
             fontsize=12, color=COLOR_SUBTLE)
    fig.text(0.07, 0.02,
             f"Bars after {LAST_SITREP_STABLE_DATE} are provisional; revisions have run "
             f"+{OBSERVED_UPWARD_REVISION_RANGE} (Sitrep reconciliation) and "
             f"{OBSERVED_DOWNWARD_REVISION_RANGE} downward (MoH definitional cleanups).",
             fontsize=12, color=COLOR_SUBTLE, style="italic")

    fig.subplots_adjust(left=0.08, right=0.92, top=0.80, bottom=0.20)
    fig.savefig(out_path, dpi=100, facecolor="white")
    plt.close(fig)


# --- Doubling-time chart -----------------------------------------------------
# Scaffold (v1). Computes trailing-window exponential-fit doubling time for
# cumulative lab-confirmed cases. R(t) proper needs more data and a serial-
# interval distribution; doubling time is the honest interim signal.

DOUBLING_WINDOW = 7   # trailing days used to fit the exponential
DOUBLING_FLOOR = 0.5  # minimum days; below this we clip and annotate
DOUBLING_CEIL = 60    # cap for display; near-flat growth would otherwise spike


def compute_doubling_times(cumulative, window=DOUBLING_WINDOW):
    """For each index i, fit log(cumulative) = a + b * t over the trailing
    `window` days ending at i, then return doubling time = ln(2) / b.

    Returns a list of (date_index, T_d_in_days) for indices where a valid
    positive growth fit could be computed. Indices with insufficient
    history, non-positive values, or zero/negative growth are dropped.
    """
    out = []
    for i in range(len(cumulative)):
        if i + 1 < window:
            continue
        window_vals = cumulative[i - window + 1: i + 1]
        # Drop windows with any zero/negative values (log undefined) or no
        # variation (zero growth → infinite doubling time).
        if any(v <= 0 for v in window_vals):
            continue
        ts = list(range(window))
        log_vals = [math.log(v) for v in window_vals]
        # Closed-form OLS slope for log(v) = a + b * t.
        n = len(ts)
        mean_t = sum(ts) / n
        mean_y = sum(log_vals) / n
        num = sum((t - mean_t) * (y - mean_y) for t, y in zip(ts, log_vals))
        den = sum((t - mean_t) ** 2 for t in ts)
        if den == 0:
            continue
        slope = num / den
        if slope <= 0:
            continue  # flat or declining: doubling time undefined / negative
        td = math.log(2) / slope
        # Clip extremes for display; the underlying value stays in the data.
        td_display = max(DOUBLING_FLOOR, min(td, DOUBLING_CEIL))
        out.append((i, td_display, td))
    return out


def render_doubling_time_chart(deltas, out_path: Path):
    """Render doubling-time chart based on cumulative lab-confirmed cases.

    Scaffold version. Single line, current-value callout, methodology
    footnote about the trailing-window exponential fit and what doubling
    time does and doesn't measure.
    """
    dates = [d["date"] for d in deltas]
    short_dates = [d[5:] for d in dates]
    cum_conf = [d["cum_conf"] for d in deltas]

    points = compute_doubling_times(cum_conf, window=DOUBLING_WINDOW)
    if not points:
        # Not enough data yet — write a placeholder image so the file exists
        # and the reader knows why.
        fig, ax = plt.subplots(figsize=(16, 9), dpi=100)
        ax.text(0.5, 0.5,
                f"Doubling-time series needs at least {DOUBLING_WINDOW} days "
                f"of positive confirmed-case growth.\nNot enough data yet.",
                ha="center", va="center", fontsize=20, color=COLOR_SUBTLE,
                transform=ax.transAxes)
        ax.set_axis_off()
        fig.savefig(out_path, dpi=100, facecolor="white")
        plt.close(fig)
        return

    fig, ax = plt.subplots(figsize=(16, 9), dpi=100)
    xs = list(range(len(dates)))

    # Plot the doubling-time series only at indices where we have a fit.
    plot_xs = [p[0] for p in points]
    plot_ys = [p[1] for p in points]

    ax.plot(plot_xs, plot_ys, color=COLOR_DOUBLING, linewidth=2.2,
            marker="o", markersize=7, markerfacecolor=COLOR_DOUBLING,
            markeredgecolor="white", markeredgewidth=1.1, zorder=5)

    # Annotate every point with its value so the reader can read off
    # specific numbers (it's a small N — currently ~5 points).
    yspan_pad = max(plot_ys) * 0.04 if plot_ys else 0.1
    for x, y, raw in points:
        clipped = raw != y
        label = f"{raw:.1f}d" + ("⁺" if clipped else "")
        ax.text(x, y + yspan_pad, label, ha="center", va="bottom",
                fontsize=14, fontweight="bold", color=COLOR_TEXT)

    # X axis: align to the full date range (not just the plotted points) so
    # the chart context matches the other two PNGs.
    ax.set_xticks(xs)
    ax.set_xticklabels(short_dates)
    ax.set_xlabel("Report date (2026)", labelpad=12)
    ax.set_ylabel("Doubling time (days)", labelpad=12)

    # Y axis: start at 0, with headroom above the highest value.
    ax.set_ylim(0, max(plot_ys) * 1.4 if plot_ys else 10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}"))
    ax.grid(axis="x", visible=False)

    # Reference lines: 2-day and 7-day doubling. 2d is roughly the lower
    # bound of a fast-growing outbreak; 7d is roughly the threshold below
    # which an outbreak is still in exponential acceleration.
    for ref_value, ref_label in [(2, "2-day doubling (fast)"),
                                  (7, "7-day doubling")]:
        if ref_value <= ax.get_ylim()[1]:
            ax.axhline(ref_value, color=COLOR_SUBTLE, linewidth=0.8,
                       linestyle="--", zorder=1, alpha=0.6)
            ax.text(xs[0], ref_value, f"  {ref_label}",
                    fontsize=11, color=COLOR_SUBTLE, va="bottom", ha="left")

    fig.suptitle("Ebola (Bundibugyo): doubling time of lab-confirmed cases",
                 fontsize=26, fontweight="bold", color=COLOR_TEXT,
                 x=0.07, ha="left", y=0.96)
    ax.set_title(
        f"Trailing {DOUBLING_WINDOW}-day exponential fit. "
        "Lower = faster spread; higher = decelerating.",
        fontsize=17, fontweight="normal", color=COLOR_SUBTLE,
        loc="left", pad=16)

    fig.text(0.07, 0.105, BYLINE, fontsize=12, color=COLOR_SUBTLE)
    fig.text(0.07, 0.075,
             "Source: WHO AFRO Weekly Sitrep, WHO Disease Outbreak News, "
             "CDC Situation Summary, Africa CDC, BNO News.",
             fontsize=12, color=COLOR_SUBTLE)
    fig.text(0.07, 0.045,
             f"Methodology: doubling time = ln(2) / b, where b is the OLS "
             f"slope of log(cumulative confirmed cases) over the trailing "
             f"{DOUBLING_WINDOW} days.",
             fontsize=12, color=COLOR_SUBTLE, style="italic")
    fig.text(0.07, 0.015,
             "R(t) proper requires a serial-interval distribution and a "
             "longer time series; this is the interim velocity signal.",
             fontsize=12, color=COLOR_SUBTLE, style="italic")

    fig.subplots_adjust(left=0.08, right=0.95, top=0.80, bottom=0.23)
    fig.savefig(out_path, dpi=100, facecolor="white")
    plt.close(fig)


# --- Entry point -------------------------------------------------------------

def main():
    import shutil

    deltas = load_data(TIMESERIES_CSV)
    if not deltas:
        raise SystemExit(f"No data rows found in {TIMESERIES_CSV}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest = deltas[-1]["date"]  # YYYY-MM-DD of the most recent row

    # Date-prefixed canonical files (committed to git for archive/history).
    dated_outputs = {
        "cases": OUTPUT_DIR / f"{latest}_ebola-cases-7d-rolling-sum.png",
        "deaths": OUTPUT_DIR / f"{latest}_ebola-deaths-7d-rolling-sum.png",
    }
    # Latest-* convenience copies so the GitHub Pages site can reference
    # stable filenames without needing to know today's date.
    latest_outputs = {
        "cases": OUTPUT_DIR / "latest-cases.png",
        "deaths": OUTPUT_DIR / "latest-deaths.png",
    }

    render_cases_chart(deltas, dated_outputs["cases"])
    render_deaths_chart(deltas, dated_outputs["deaths"])
    # Doubling-time chart is disabled in the publication path while early
    # confirmed-case figures are still heavily revised by WHO Sitrep
    # reconciliation. The chart code (render_doubling_time_chart and
    # compute_doubling_times) is kept above for future re-enabling once
    # data is less provisional. To re-enable, restore the dated + latest
    # "doubling" entries above and add:
    #     render_doubling_time_chart(deltas, dated_outputs["doubling"])

    for key, dated in dated_outputs.items():
        shutil.copyfile(dated, latest_outputs[key])

    for path in (*dated_outputs.values(), *latest_outputs.values()):
        print(f"Wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

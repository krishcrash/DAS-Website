"""Analytics charts for /analytics/ and /analytics/details/.

Adapted from the original website_analysis.py (kept in scripts/legacy/). The
calculations are the same; what changed:

  * Paths are relative to the repo, so it runs locally and in GitHub Actions.
  * pandas 2 compatible (month bucketing no longer uses astype("datetime64[M]")).
  * Instead of one standalone HTML file per chart (embedded with iframes), it
    writes a single JSON file of Plotly figures + "views" (what the old
    dropdown buttons switched between). The site renders them with its own
    controls, dark theme, responsive sizing and a data-table fallback.
  * Member codes are shown as names.
  * Per-film tables/callouts are no longer generated here — review pages
    compute those natively from build/data/scores.json.
  * Encodings adjusted for 9 active members (more than a colour palette can
    safely distinguish): stacked-by-member bars became a member × month heat
    grid, and the all-members radar became one small radar per member.

Output: build/data/charts.json  (mounted into Hugo as hugo.Data.charts)
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.utils import PlotlyJSONEncoder

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "master-data"
OUT = ROOT / "build" / "data" / "charts.json"

pio.templates.default = "none"  # keep the JSON lean; the theme is applied below

# Site palette (assets/css/tokens.css). One accent for single-series charts;
# warm/cool pair for the diverging chart; neutral for "society average".
# Chart marks validated as a pair against the page ground #0b0a09 with the
# dataviz palette validator (lightness band, chroma floor, CVD, contrast).
ACCENT = "#c87f1e"
COOL = "#4a9cc9"
NEUTRAL = "#8a8174"
INK = "#0b0a09"
BONE = "#ede5d6"
GRID = "#2a2521"
AXIS = "#4a423b"
MUTED = "#8a8174"
TEXT = "#bdb3a2"
FONT = "Archivo, 'Helvetica Neue', Arial, sans-serif"

LAST_YEAR_WINDOW = 1  # years; the "last year" charts and the radar use this window


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def minus_years(d: dt.datetime, years: int) -> dt.datetime:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year - years, day=28)


def month_start(s: pd.Series) -> pd.Series:
    return s.dt.to_period("M").dt.to_timestamp()


def short(label: str, n: int = 24) -> str:
    return label if len(label) <= n else label[: n - 1].rstrip() + "…"


def theme(fig: go.Figure, height: int, **layout) -> go.Figure:
    axis = dict(
        gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, zerolinewidth=1,
        tickfont=dict(color=MUTED, size=12), title=dict(font=dict(color=MUTED, size=12)),
        automargin=True, fixedrange=True, showline=False, ticks="",
    )
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=TEXT),
        margin=dict(l=4, r=24, t=8, b=8),
        hoverlabel=dict(bgcolor=BONE, bordercolor=BONE, font=dict(family=FONT, color=INK, size=13)),
        showlegend=False,
        dragmode=False,
        bargap=0.5,
        xaxis=axis,
        yaxis=axis,
    )
    fig.update_layout(**layout)
    return fig


def fig_json(fig: go.Figure) -> dict:
    return json.loads(fig.to_json())


def plain(obj):
    """Round-trip through Plotly's encoder (numpy, Timestamps → JSON types)."""
    return json.loads(json.dumps(obj, cls=PlotlyJSONEncoder))


def hbar(labels, values, full_labels=None, fmt=".2f", color=ACCENT):
    full_labels = full_labels if full_labels is not None else labels
    return go.Bar(
        x=list(values), y=[short(str(l)) for l in labels], orientation="h",
        marker=dict(color=color, cornerradius=4),
        customdata=list(full_labels),
        hovertemplate=f"<b>%{{customdata}}</b><br>%{{x:{fmt}}}<extra></extra>",
        cliponaxis=False,
    )


def bar_height(n: int) -> int:
    return max(200, 32 * n + 48)   # ~16px bars at bargap 0.5


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def load():
    raw = pd.read_csv(MASTER / "ratings_by_metric.csv")
    # Blank scores are placeholders (not submitted yet) — see build_data.py.
    raw["Score"] = pd.to_numeric(raw["Score"], errors="coerce")
    raw = raw.dropna(subset=["Score"])
    raw["date"] = pd.to_datetime(raw["date"], format="%d/%m/%Y")
    raw["Metric"] = raw["Metric"].str.strip().str.lower()

    users = pd.read_csv(MASTER / "config_users.csv")
    users.columns = users.columns.str.strip()
    active = users.loc[users["include"] == 1, "user_code"].tolist()
    names = dict(zip(users["user_code"], users["full_name"]))

    maxes = pd.read_csv(MASTER / "max_ratings.csv")
    maxes["Metric"] = maxes["Metric"].str.strip().str.lower()
    max_total = float(maxes["max_score"].sum())
    metric_max = dict(zip(maxes["Metric"].str.capitalize(), maxes["max_score"]))

    # Show films by their review's display title (build_data.py runs first).
    films_json = ROOT / "build" / "data" / "films.json"
    if films_json.exists():
        titles = {f["score_key"]: f["title"] for f in json.loads(films_json.read_text(encoding="utf-8"))
                  if f.get("score_key") and f.get("title")}
        raw["movie"] = raw["movie"].map(lambda m: titles.get(m, m))

    df = raw[raw["user"].isin(active)].copy()
    return df, users, active, names, max_total, metric_max


# --------------------------------------------------------------------------
# /analytics/ (formerly analysis1/)
# --------------------------------------------------------------------------

def last_year_chart(df, active, names, max_total):
    now = dt.datetime.now()
    d = df[df["date"] >= minus_years(now, LAST_YEAR_WINDOW)].copy()
    d["date"] = month_start(d["date"])
    movie_totals = d.groupby(["user", "movie", "date"])["Score"].sum().reset_index()
    monthly = movie_totals.groupby(["user", "date"])["Score"].mean().reset_index()
    group = monthly.groupby("date")["Score"].mean().reset_index()

    def trace_for(frame):
        frame = frame.sort_values("date")
        return frame["date"].dt.strftime("%Y-%m-%d").tolist(), frame["Score"].round(2).tolist()

    x, y = trace_for(group)
    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="lines+markers",
        line=dict(width=2, color=ACCENT, shape="linear"),
        marker=dict(size=9, color=ACCENT, line=dict(width=2, color=INK)),
        hovertemplate="%{x|%B %Y}<br><b>%{y:.2f}</b><extra></extra>",
    ))
    theme(fig, 360, yaxis=dict(range=[-0.5, max_total + 0.5], title=dict(text="Average total score")),
          xaxis=dict(tickformat="%b %Y", dtick="M1"))

    views = [{"label": "Society", "restyle": {"x": [x], "y": [y]}}]
    for u in active:
        u_df = monthly[monthly["user"] == u]
        if not u_df.empty:
            ux, uy = trace_for(u_df)
            views.append({"label": names.get(u, u), "restyle": {"x": [ux], "y": [uy]}})
    return {
        "title": "The last twelve months",
        "note": "Average total score per month, across the society or for one member.",
        "control": "Whose scores",
        "table": ["Month", "Average"],
        "figure": fig_json(fig),
        "views": views,
    }


def top_ten_chart(df, active, names, max_total, mode="top"):
    movie_totals = df.groupby(["user", "movie"])["Score"].sum().reset_index()
    avg = movie_totals.groupby("movie")["Score"].mean().reset_index()
    ascending = mode == "bottom"

    def pick(frame):
        # Ties broken alphabetically so output is identical across pandas versions.
        f = frame.sort_values(["Score", "movie"], ascending=[ascending, True], kind="mergesort").head(10)
        return f["movie"].tolist(), f["Score"].round(2).tolist()

    labels, values = pick(avg)
    fig = go.Figure(hbar(labels, values))
    theme(fig, bar_height(10), xaxis=dict(range=[0, max_total], title=dict(text="Total score")),
          yaxis=dict(autorange="reversed"))
    views = [{"label": "Society", "restyle": {"x": [values], "y": [[short(l) for l in labels]], "customdata": [labels]}}]
    for u in active:
        u_df = movie_totals[movie_totals["user"] == u]
        if not u_df.empty:
            l, v = pick(u_df)
            views.append({
                "label": names.get(u, u),
                "restyle": {"x": [v], "y": [[short(s) for s in l]], "customdata": [l]},
                "relayout": {"height": bar_height(len(l))},
            })
    views[0]["relayout"] = {"height": bar_height(len(labels))}
    return {
        "title": "The top ten" if mode == "top" else "The bottom ten",
        "note": ("Highest-scoring films by average total — or by one member's own scores."
                 if mode == "top" else
                 "Lowest-scoring films by average total — or by one member's own scores."),
        "control": "Whose scores",
        "table": ["Film", "Total"],
        "figure": fig_json(fig),
        "views": views,
    }


def attendance_chart(df, names):
    att = df.groupby("user")["movie"].nunique().reset_index()
    att = att.sort_values(["movie", "user"], ascending=[False, True], kind="mergesort")
    labels = [names.get(u, u) for u in att["user"]]
    fig = go.Figure(hbar(labels, att["movie"].tolist(), fmt="d"))
    theme(fig, bar_height(len(labels)), yaxis=dict(autorange="reversed"),
          xaxis=dict(title=dict(text="Films rated"), dtick=5))
    return {
        "title": "Attendance",
        "note": "How many films each active member has scored.",
        "table": ["Member", "Films"],
        "figure": fig_json(fig),
        "views": [],
    }


def score_over_time_chart(df, active, names):
    """Member × month grid of each member's total score (was a 9-colour stacked bar)."""
    now = dt.datetime.now()
    d = df[df["date"] >= minus_years(now, LAST_YEAR_WINDOW)].copy()
    d["date"] = month_start(d["date"])
    totals = d.groupby(["user", "date"])["Score"].sum().reset_index()
    months = sorted(totals["date"].unique())
    members = [u for u in active if u in set(totals["user"])]
    z, text = [], []
    for u in members:
        row, trow = [], []
        for m in months:
            v = totals[(totals["user"] == u) & (totals["date"] == m)]["Score"]
            val = round(float(v.iloc[0]), 2) if len(v) else None
            row.append(val)
            trow.append("" if val is None else f"{val:g}")
        z.append(row)
        text.append(trow)
    xlabels = [pd.Timestamp(m).strftime("%b %Y") for m in months]
    ylabels = [names.get(u, u) for u in members]
    fig = go.Figure(go.Heatmap(
        z=z, x=xlabels, y=ylabels,
        colorscale=[[0, "#2e2419"], [1, ACCENT]],
        zmin=0, showscale=False, xgap=2, ygap=2, hoverongaps=False,
        hovertemplate="<b>%{y}</b> · %{x}<br>%{z:.2f}<extra></extra>",
    ))
    # Cell labels: dark ink on bright cells, light ink on dark ones.
    zmax = max((v for row in z for v in row if v is not None), default=1) or 1
    for yi, row in enumerate(z):
        for xi, v in enumerate(row):
            if v is not None:
                fig.add_annotation(x=xlabels[xi], y=ylabels[yi], text=f"{v:g}", showarrow=False,
                                   font=dict(family=FONT, size=13, color=INK if v / zmax > 0.55 else BONE))
    theme(fig, max(240, 40 * len(ylabels) + 60), yaxis=dict(autorange="reversed", showgrid=False),
          xaxis=dict(showgrid=False, side="top"))
    return {
        "title": "Score over time",
        "note": "Each member's total for the month's film. Blank means they didn't score it.",
        "table": ["Member"] + xlabels,
        "figure": fig_json(fig),
        "views": [],
    }


# --------------------------------------------------------------------------
# /analytics/details/ (formerly analysis2/)
# --------------------------------------------------------------------------

def metric_views(final_df, value_col, label_col, max_total, metric_max, fmt_title, fixed_range=True):
    metrics = ["Mean"] + [m for m in ["Enjoyable", "Plot", "Acting", "Camera", "Themes", "Music", "Casting", "Wildcard"]
                          if m in set(final_df["Metric"])]
    views = []
    for m in metrics:
        m_df = final_df[final_df["Metric"] == m].sort_values([value_col, label_col], ascending=[False, True], kind="mergesort")
        labels = m_df[label_col].tolist()
        vals = m_df[value_col].round(3).tolist()
        relayout = {"height": bar_height(len(labels)), "xaxis.title.text": fmt_title(m)}
        if fixed_range:
            hi = max_total if m == "Mean" else float(metric_max.get(m, 1.0))
            lo = -hi if m == "Wildcard" else 0
            relayout["xaxis.range"] = [lo, hi]
        views.append({"label": "Total" if m == "Mean" else m,
                      "restyle": {"x": [vals], "y": [labels], "customdata": [labels]},
                      "relayout": relayout})
    return views


def voter_score_chart(df, names, max_total, metric_max):
    movie_totals = df.groupby(["user", "movie"])["Score"].sum().reset_index()
    total_avg = movie_totals.groupby("user")["Score"].mean().reset_index()
    total_avg["Metric"] = "Mean"
    metric_avg = df.groupby(["user", "Metric"])["Score"].mean().reset_index()
    final = pd.concat([total_avg, metric_avg], axis=0)
    final["Metric"] = final["Metric"].str.capitalize()
    final["Name"] = final["user"].map(lambda u: names.get(u, u))
    views = metric_views(final, "Score", "Name", max_total, metric_max, lambda m: f"Average {m.lower() if m != 'Mean' else 'total'} score")
    first = views[0]
    fig = go.Figure(hbar(first["restyle"]["y"][0], first["restyle"]["x"][0]))
    theme(fig, first["relayout"]["height"], yaxis=dict(autorange="reversed"),
          xaxis=dict(range=first["relayout"]["xaxis.range"], title=dict(text=first["relayout"]["xaxis.title.text"])))
    return {
        "title": "Generosity",
        "note": "Each member's average score — overall, or in one category.",
        "control": "Category",
        "table": ["Member", "Average"],
        "figure": fig_json(fig),
        "views": views,
    }


def median_diff_chart(df, names):
    med = df.groupby(["Metric", "movie"])["Score"].median().reset_index().rename(columns={"Score": "median_metric"})
    dd = df.merge(med, on=["Metric", "movie"])
    dd["delta"] = dd["Score"] - dd["median_metric"]
    metric_delta = dd.groupby(["user", "Metric"])["delta"].mean().reset_index()
    movie_total = dd.groupby(["user", "movie"])["delta"].sum().reset_index()
    mean_delta = movie_total.groupby("user")["delta"].mean().reset_index()
    mean_delta["Metric"] = "Mean"
    final = pd.concat([mean_delta, metric_delta], axis=0)
    final["Metric"] = final["Metric"].str.capitalize()
    final["Name"] = final["user"].map(lambda u: names.get(u, u))
    views = metric_views(final, "delta", "Name", 0, {}, lambda m: "Average difference from the median", fixed_range=False)
    for v in views:
        v["restyle"]["marker.color"] = [[ACCENT if x >= 0 else COOL for x in v["restyle"]["x"][0]]]
        v["relayout"]["xaxis.autorange"] = True
    first = views[0]
    fig = go.Figure(hbar(first["restyle"]["y"][0], first["restyle"]["x"][0], fmt="+.2f",
                         color=first["restyle"]["marker.color"][0]))
    theme(fig, first["relayout"]["height"], yaxis=dict(autorange="reversed"),
          xaxis=dict(zeroline=True, zerolinecolor=MUTED, zerolinewidth=1,
                     title=dict(text="Average difference from the median")))
    return {
        "title": "Against the grain",
        "note": "How far each member sits above (warm) or below (cool) the median score on the same films.",
        "control": "Category",
        "legend": [{"label": "Above the median", "color": ACCENT}, {"label": "Below the median", "color": COOL}],
        "table": ["Member", "Difference"],
        "figure": fig_json(fig),
        "views": views,
    }


def nominator_chart(df, users, max_total, metric_max):
    name_map = dict(zip(users["full_name"], users["user_code"]))
    active_codes = users.loc[users["include"] == 1, "user_code"].tolist()
    d = df.copy()
    d["code"] = d["list_user"].map(name_map)
    d = d[d["code"].isin(active_codes)].dropna(subset=["code"])
    clean = d.groupby(["list_user", "movie", "Metric"])["Score"].mean().reset_index()
    metric_avg = clean.groupby(["list_user", "Metric"])["Score"].mean().reset_index()
    movie_totals = clean.groupby(["list_user", "movie"])["Score"].sum().reset_index()
    total_avg = movie_totals.groupby("list_user")["Score"].mean().reset_index()
    total_avg["Metric"] = "Mean"
    final = pd.concat([total_avg, metric_avg], axis=0)
    final["Metric"] = final["Metric"].str.capitalize()
    views = metric_views(final, "Score", "list_user", max_total, metric_max,
                         lambda m: f"Average {m.lower() if m != 'Mean' else 'total'} score of their picks")
    first = views[0]
    fig = go.Figure(hbar(first["restyle"]["y"][0], first["restyle"]["x"][0]))
    theme(fig, first["relayout"]["height"], yaxis=dict(autorange="reversed"),
          xaxis=dict(range=first["relayout"]["xaxis.range"], title=dict(text=first["relayout"]["xaxis.title.text"])))
    return {
        "title": "Taste test",
        "note": "How the society scored the films each member nominated.",
        "control": "Category",
        "table": ["Nominator", "Average"],
        "figure": fig_json(fig),
        "views": views,
    }


def radar_chart(df, active, names, metric_max):
    """Small multiples: one radar per member (member vs society average)."""
    now = dt.datetime.now()
    d = df[df["date"] >= minus_years(now, LAST_YEAR_WINDOW)].copy().sort_values("date", ascending=False)
    order = ["enjoyable", "plot", "acting", "camera", "themes", "music", "casting", "wildcard"]
    cats = [m for m in order if m in set(d["Metric"])]
    maxes = {m.lower(): v for m, v in metric_max.items()}
    # Wildcard runs -max..+max; map to 0–100% so the shape stays comparable.
    d["pct"] = d.apply(lambda r: ((r["Score"] + maxes[r["Metric"]]) / (2 * maxes[r["Metric"]]) * 100)
                       if r["Metric"] == "wildcard" else r["Score"] / maxes[r["Metric"]] * 100, axis=1)

    members = [u for u in active if u in set(d["user"])]

    def profile(frame):
        return [round(float(frame[frame["Metric"] == c]["pct"].mean()), 1) if not frame[frame["Metric"] == c].empty else None
                for c in cats]

    views = []
    for label, frame in [("All films", d)] + [(m, d[d["movie"] == m]) for m in d["movie"].unique()]:
        views.append({
            "label": label,
            "society": profile(frame),
            "members": {u: (profile(frame[frame["user"] == u]) if not frame[frame["user"] == u].empty else None)
                        for u in members},
        })
    return {
        "kind": "radar-multiples",
        "title": "Fingerprints",
        "note": "Each member's scores as a share of each category's maximum, against the society average. "
                "Covers the last twelve months.",
        "control": "Film",
        "categories": [c.capitalize() for c in cats],
        "members": [{"code": u, "name": names.get(u, u)} for u in members],
        "legend": [{"label": "Member", "color": ACCENT}, {"label": "Society average", "color": NEUTRAL}],
        "colors": {"member": ACCENT, "society": NEUTRAL, "grid": GRID, "text": MUTED},
        "views": views,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    df, users, active, names, max_total, metric_max = load()
    charts = {
        "last_year": last_year_chart(df, active, names, max_total),
        "top_ten": top_ten_chart(df, active, names, max_total, "top"),
        "bottom_ten": top_ten_chart(df, active, names, max_total, "bottom"),
        "attendance": attendance_chart(df, names),
        "score_over_time": score_over_time_chart(df, active, names),
        "generosity": voter_score_chart(df, names, max_total, metric_max),
        "median_diff": median_diff_chart(df, names),
        "nominators": nominator_chart(df, users, max_total, metric_max),
        "radar": radar_chart(df, active, names, metric_max),
    }
    charts = plain(charts)
    charts["_generated"] = dt.datetime.now().isoformat(timespec="seconds")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(charts, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(charts) - 1} charts → {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

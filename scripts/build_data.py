"""Build the site's master dataset from the score ledger + review Markdown.

Runs on every build (locally and in GitHub Actions), before Hugo.

Inputs
  master-data/ratings_by_metric.csv   one row per user × film × category
  master-data/config_users.csv        member codes, names, include flag
  master-data/max_ratings.csv         max score per category
  content/reviews/*.md                editorial front matter (joined by score_key)

Outputs (git-ignored, mounted into Hugo's data/ by hugo.toml)
  build/data/scores.json   per-film score analysis, keyed by ledger film name;
                           review templates look themselves up by score_key
  build/data/films.json    unified master dataset: every review's editorial
                           fields + its computed scores, newest first

Every number the site shows — ranks, category means, consensus, The Fan,
The Cynic, The Specialist — is computed here, so editing the CSV is all it
takes to update the site.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "master-data"
REVIEWS_DIR = ROOT / "content" / "reviews"
OUT_DIR = ROOT / "build" / "data"

# The existing analytics (and the old WordPress callouts) only count members
# flagged include=1 in config_users.csv. Keep the site consistent with that.
ACTIVE_MEMBERS_ONLY = True

# Consensus bands on the standard deviation of reviewers' total scores.
CONSENSUS_BANDS = [
    (0.6, "High Agreement", "agree"),
    (1.5, "Some Debate", "debate"),
    (float("inf"), "Highly Controversial", "controversial"),
]


def r2(x: float) -> float:
    """Round half-up to 2dp (Python's round() is half-even: 0.425 -> 0.42)."""
    return float(Decimal(repr(float(x))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def load_ledger() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ratings = pd.read_csv(MASTER / "ratings_by_metric.csv")
    ratings["date"] = pd.to_datetime(ratings["date"], format="%d/%m/%Y")
    ratings["Metric"] = ratings["Metric"].str.strip().str.lower()

    users = pd.read_csv(MASTER / "config_users.csv")
    users.columns = users.columns.str.strip()
    users = users.apply(lambda s: s.str.strip() if s.dtype == object else s)

    maxes = pd.read_csv(MASTER / "max_ratings.csv")
    maxes["Metric"] = maxes["Metric"].str.strip().str.lower()
    return ratings, users, maxes


def analyse(ratings: pd.DataFrame, users: pd.DataFrame, maxes: pd.DataFrame) -> dict:
    names = dict(zip(users["user_code"], users["full_name"]))
    active = users.loc[users["include"] == 1, "user_code"].tolist()
    df = ratings[ratings["user"].isin(active)] if ACTIVE_MEMBERS_ONLY else ratings

    order = (ratings.groupby("Metric")["metric_order"].min().sort_values().index.tolist())
    max_map = dict(zip(maxes["Metric"], maxes["max_score"]))
    max_total = float(maxes["max_score"].sum())
    metrics = [{"key": m, "label": m.capitalize(), "max": float(max_map.get(m, 0))} for m in order]
    # Society-wide habits per category (for the scoring guide page).
    for m in metrics:
        scores = df.loc[df["Metric"] == m["key"], "Score"]
        m["society_mean"] = r2(scores.mean()) if len(scores) else None
        m["share_max"] = r2((scores >= m["max"]).mean() * 100) if len(scores) else None

    # Per reviewer per film totals, then film means (same as the Plotly script).
    user_totals = df.groupby(["movie", "user"])["Score"].sum().reset_index()
    film_means = user_totals.groupby("movie")["Score"].mean()
    ranks = film_means.rank(method="min", ascending=False)
    spread = user_totals.groupby("movie")["Score"].std().fillna(0)
    metric_means = df.groupby(["movie", "Metric"])["Score"].mean()

    films: dict[str, dict] = {}
    for movie, mdf in df.groupby("movie"):
        totals = user_totals[user_totals["movie"] == movie]
        means = {m: r2(metric_means.get((movie, m), 0.0)) for m in order}
        total = r2(film_means[movie])

        # Top category: best mean as a share of its max, excluding Enjoyable.
        pct = {m: means[m] / max_map[m] for m in order if m != "enjoyable" and max_map.get(m)}
        top = max(pct, key=pct.get) if pct else None

        sd = float(spread[movie])
        band = next(b for b in CONSENSUS_BANDS if sd < b[0])

        fan = totals.loc[totals["Score"].idxmax()]
        cynic = totals.loc[totals["Score"].idxmin()]

        # Specialist: highest single-category % of max (excl. Enjoyable);
        # ties go to the reviewer with the lower overall total.
        spec_df = mdf[mdf["Metric"] != "enjoyable"].copy()
        spec_df["perc"] = spec_df.apply(lambda x: x["Score"] / max_map.get(x["Metric"], 1), axis=1)
        spec_df = spec_df.merge(totals[["user", "Score"]], on="user", suffixes=("", "_total"))
        spec = spec_df.sort_values(["perc", "Score_total"], ascending=[False, True]).iloc[0]

        pivot = mdf.pivot_table(index="user", columns="Metric", values="Score", aggfunc="mean")
        reviewers = []
        for code, row in pivot.iterrows():
            scores = {m: r2(row.get(m, 0.0)) for m in order}
            reviewers.append({
                "user": code,
                "name": names.get(code, code),
                "scores": scores,
                "total": r2(sum(row.get(m, 0.0) for m in order)),
            })
        reviewers.sort(key=lambda x: (-x["total"], x["user"]))

        person = lambda row: {"user": row["user"], "name": names.get(row["user"], row["user"]),
                              "total": r2(row["Score"])}
        films[movie] = {
            "date": mdf["date"].min().date().isoformat(),
            "list_user": mdf["list_user"].iloc[0],
            "rank": int(ranks[movie]),
            "rank_of": int(len(film_means)),
            "total": total,
            "total_pct": r2(total / max_total * 100),
            "means": means,
            "diff": {m: r2(max_map[m] - means[m]) for m in order},
            "top_category": {"key": top, "label": top.capitalize(), "pct": r2(pct[top] * 100)} if top else None,
            "consensus": {"label": band[1], "level": band[2], "sd": r2(sd)},
            "fan": person(fan),
            "cynic": person(cynic),
            "specialist": {
                "user": spec["user"],
                "name": names.get(spec["user"], spec["user"]),
                "metric": spec["Metric"],
                "label": spec["Metric"].capitalize(),
                "pct": r2(spec["perc"] * 100),
            },
            "reviewer_count": len(reviewers),
            "reviewers": reviewers,
        }

    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "metrics": metrics,
        "max_total": max_total,
        "members": {
            row.user_code: {"name": row.full_name, "active": bool(row.include == 1)}
            for row in users.itertuples()
        },
        "film_count": len(films),
        "films": films,
    }


def read_front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    _, fm, _ = text.split("---", 2)
    data = yaml.safe_load(fm) or {}
    # YAML turns bare dates into date objects; keep them JSON-friendly.
    return {k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in data.items()}


def unify(scores: dict) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    films: list[dict] = []
    seen: set[str] = set()
    for path in sorted(REVIEWS_DIR.glob("*.md")):
        if path.name.startswith("_"):
            continue
        fm = read_front_matter(path)
        if fm.get("draft"):
            continue
        key = fm.get("score_key") or fm.get("title")
        seen.add(key)
        s = scores["films"].get(key)
        if s is None:
            warnings.append(f"{path.name}: score_key '{key}' not found in ratings_by_metric.csv")
        films.append({
            "slug": path.stem,
            "url": f"/reviews/{path.stem}/",
            **{k: fm.get(k) for k in ("title", "date", "score_key", "director", "year", "nominator",
                                      "nomination_month", "nominations", "poster", "banner")},
            "scores": s,
        })
    for key in sorted(set(scores["films"]) - seen):
        warnings.append(f"'{key}' has scores but no review file in content/reviews/")
    films.sort(key=lambda f: str(f.get("date") or ""), reverse=True)
    return films, warnings


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ratings, users, maxes = load_ledger()
    scores = analyse(ratings, users, maxes)
    films, warnings = unify(scores)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_DIR / "films.json").write_text(json.dumps(films, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Scored {scores['film_count']} films (max total {scores['max_total']:g}); "
          f"{len(films)} reviews in master dataset → {OUT_DIR.relative_to(ROOT)}")
    for w in warnings:
        # GitHub Actions renders ::warning lines as annotations on the run.
        print(f"::warning::{w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""One-off migration: WordPress export -> Hugo review Markdown.

Reads the WordPress XML export and writes one file per published review to
content/reviews/<slug>.md, containing only *editorial* data:

    title, director, year, nominator, nomination month, the nomination
    shortlist with vote counts, poster/banner paths, legacy URL aliases,
    and the plot synopsis (converted to Markdown).

Scores are deliberately NOT migrated: the WordPress score tables are stale
copies. Every number on the new site is computed from the score CSV by
scripts/build_data.py on each build, joined via each review's `score_key`.

After migration the Markdown files become the source of truth for editorial
content, so existing files are never overwritten unless --force is passed.

Usage:
    py scripts/migrate_wordpress.py                    # write reviews + report
    py scripts/migrate_wordpress.py --download-images  # also fetch media
    py scripts/migrate_wordpress.py --force            # overwrite existing .md
"""

from __future__ import annotations

import argparse
import csv
import difflib
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "master-data"
XML_GLOB = "wordpress/*.xml"
RATINGS_CSV = MASTER / "ratings_by_metric.csv"
USERS_CSV = MASTER / "config_users.csv"
FACTS_CSV = MASTER / "film_facts.csv"
REVIEWS_DIR = ROOT / "content" / "reviews"
IMAGES_DIR = ROOT / "assets" / "images"
REPORT_PATH = MASTER / "wordpress" / "migration-report.md"

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "wp": "http://wordpress.org/export/1.2/",
}

# Obvious typos in nomination shortlists, fixed on the way through.
NOMINATION_TYPOS = {
    "Se7ev": "Se7en",
    "Cit of God": "City of God",
    "Thone of Blood": "Throne of Blood",
    "Ford Vs Ferarri": "Ford v Ferrari",
    "Ford Vs Ferrari": "Ford v Ferrari",
    "The Discreet Charm of The Borgousise": "The Discreet Charm of the Bourgeoisie",
}

MONTHS = {m.lower(): i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


# --------------------------------------------------------------------------
# HTML -> Markdown (just the subset WordPress block content uses)
# --------------------------------------------------------------------------

class MarkdownConverter(HTMLParser):
    SKIP = {"iframe", "script", "style", "figure", "table", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.buf: list[str] = []
        self.skip_depth = 0
        self.list_stack: list[str] = []
        self.href: str | None = None
        self.heading = 0
        self.inline: list[tuple[str, int]] = []  # open emphasis: (marker, buf index)

    def _open(self, marker: str) -> None:
        self.inline.append((marker, len(self.buf)))

    def _close(self, marker: str) -> None:
        """Wrap text since the matching open tag in `marker`, moving whitespace
        outside it — WordPress often leaves spaces inside <strong>, which
        Markdown won't render as bold ("**Teddy **(")."""
        for i in range(len(self.inline) - 1, -1, -1):
            if self.inline[i][0] == marker:
                _, idx = self.inline.pop(i)
                break
        else:
            return
        inner = "".join(self.buf[idx:])
        core = inner.strip()
        lead = " " if inner[:1].isspace() else ""
        trail = " " if inner[-1:].isspace() else ""
        before = "".join(self.buf[:idx])[-1:]
        if core and before.isalnum() and not lead:
            lead = " "  # "that**Michelle**" would not parse as bold
        self.buf[idx:] = [lead + (f"{marker}{core}{marker}" if core else "") + trail]

    def _flush(self, prefix: str = "") -> None:
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if prefix.startswith("#"):
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # headings are bold already
        if text:
            self.blocks.append(prefix + text)
        self.buf = []
        self.inline = []

    def handle_starttag(self, tag, attrs):
        if self.skip_depth or tag in self.SKIP:
            self.skip_depth += tag in self.SKIP
            return
        a = dict(attrs)
        if tag in ("p", "div", "blockquote"):
            self._flush()
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()
            self.heading = 3
        elif tag in ("ul", "ol"):
            self._flush()
            self.list_stack.append(tag)
        elif tag == "li":
            self._flush()
        elif tag == "br":
            self.buf.append(" ")
        elif tag in ("strong", "b"):
            self._open("**")
        elif tag in ("em", "i"):
            self._open("_")
        elif tag == "a":
            self.href = a.get("href")
            self.buf.append("[")

    def handle_endtag(self, tag):
        if self.skip_depth:
            self.skip_depth -= tag in self.SKIP
            return
        if tag in ("p", "div", "blockquote"):
            self._flush("> " if tag == "blockquote" else "")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush("#" * self.heading + " ")
            self.heading = 0
        elif tag == "li":
            marker = "1. " if self.list_stack and self.list_stack[-1] == "ol" else "- "
            self._flush(marker)
            if self.blocks:
                self.blocks[-1] = "\x00" + self.blocks[-1]  # mark as list item
        elif tag in ("ul", "ol"):
            self._flush()
            if self.list_stack:
                self.list_stack.pop()
        elif tag in ("strong", "b"):
            self._close("**")
        elif tag in ("em", "i"):
            self._close("_")
        elif tag == "a":
            self.buf.append(f"]({self.href})" if self.href else "]")
            self.href = None

    def handle_data(self, data):
        if not self.skip_depth:
            self.buf.append(data)

    def markdown(self) -> str:
        self._flush()
        out: list[str] = []
        for block in self.blocks:
            is_item = block.startswith("\x00")
            block = block.lstrip("\x00")
            if out and not (is_item and out[-1].startswith("\x00")):
                out.append("")
            out.append(("\x00" if is_item else "") + block)
        return "\n".join(line.lstrip("\x00") for line in out).strip() + "\n"


def html_to_markdown(fragment: str) -> str:
    fragment = re.sub(r"<!--.*?-->", "", fragment, flags=re.S)
    conv = MarkdownConverter()
    conv.feed(fragment)
    conv.close()
    return conv.markdown()


def strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


# --------------------------------------------------------------------------
# Parsing the review post body
# --------------------------------------------------------------------------

@dataclass
class Nomination:
    film: str
    votes: int | None = None
    nominated_by: str | None = None
    winner: bool = False
    tiebreak: bool = False
    marked: bool = False  # highlighted in WordPress


@dataclass
class Review:
    wp_id: str
    slug: str
    title: str
    post_date: str
    body: str
    thumbnail_id: str | None
    categories: list[str]
    nominator: str | None = None
    nomination_month: str | None = None
    nominations: list[Nomination] = field(default_factory=list)
    synopsis_md: str = ""
    director: str | None = None
    year: int | None = None
    notes: list[str] = field(default_factory=list)


def split_sections(body: str) -> tuple[str, str]:
    """Return (pre-synopsis HTML, synopsis HTML)."""
    heads = list(re.finditer(r"<h2[^>]*>(.*?)</h2>", body, re.S))
    syn = next((h for h in heads if "synopsis" in strip_tags(h.group(1)).lower()), None)
    if not syn:
        return body, ""
    after = [h for h in heads if h.start() > syn.end()]
    end = after[0].start() if after else len(body)
    return body[: syn.start()], body[syn.end(): end]


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def clean_film_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip(" -–")
    return NOMINATION_TYPOS.get(name, name)


def parse_nominations(pre: str, review: Review) -> None:
    items = re.findall(r"<li[^>]*>(.*?)</li>", pre, re.S)
    for raw in items:
        marked = "<mark" in raw
        text = strip_tags(raw)
        star = text.endswith("*")
        text = text.rstrip("*").strip()
        nom = Nomination(film=text, marked=marked, tiebreak=star)
        if m := re.match(r"^(.+?)\s*-\s*(\d+)\s*votes?$", text, re.I):
            nom.film, nom.votes = m.group(1), int(m.group(2))
        elif m := re.match(r"^(.+?)\s*-\s*([A-Z]{2})\s+Nominated$", text):
            nom.film, nom.nominated_by = m.group(1), m.group(2)
        nom.film = clean_film_name(nom.film)
        review.nominations.append(nom)

    if not review.nominations:
        review.notes.append("no nomination list found")
        return

    # The screened film is the entry matching this review's title, not
    # necessarily the highlighted one (highlights were sometimes copy-pasted).
    target = normalise(review.title)
    scores = [difflib.SequenceMatcher(None, normalise(n.film), target).ratio()
              for n in review.nominations]
    best = max(range(len(scores)), key=scores.__getitem__)
    if scores[best] >= 0.8:
        winner = review.nominations[best]
        marked = next((n for n in review.nominations if n.marked), None)
        if marked and marked is not winner:
            review.notes.append(
                f"WordPress highlighted '{marked.film}', but '{winner.film}' is the reviewed film — used the latter")
    else:
        winner = next((n for n in review.nominations if n.marked), review.nominations[-1])
        review.notes.append(
            f"no nomination matched the title; renamed highlighted entry '{winner.film}' → '{review.title}'")
    winner.film = review.title if scores[best] < 1 else winner.film
    winner.winner = True


def parse_nominator(pre: str, review: Review) -> None:
    for p in re.findall(r"<p[^>]*>(.*?)</p>", pre, re.S):
        text = strip_tags(p)
        m = re.search(r"Nominated By\s+([A-Z]{2})", text, re.I)
        if not m:
            continue
        review.nominator = m.group(1).upper()
        label = text[: m.start()]
        mm = re.search(r"([A-Za-z]{3,})\s*['’]?\s*(\d{2}(?:\d{2})?)", label)
        if mm and mm.group(1)[:3].lower() in MONTHS:
            year = int(mm.group(2))
            year = year + 2000 if year < 100 else year
            review.nomination_month = f"{year}-{MONTHS[mm.group(1)[:3].lower()]:02d}"
        else:
            review.notes.append(f"could not parse nomination month from '{label.strip()}'")
        return
    # Fall back to the "XX Nominated" category.
    for cat in review.categories:
        if m := re.match(r"^([A-Z]{2}) Nominated$", cat):
            review.nominator = m.group(1)
            review.notes.append("nominator taken from category (no 'Nominated By' line)")
            return
    review.notes.append("no nominator found")


DIRECTED_BY = re.compile(
    r"[Dd]irected by (?:and starring )?"
    # A token is an initial ("J.") or a capitalised word; a trailing full stop
    # after a word ends the sentence, so it isn't part of the name.
    r"((?:[A-Z]\.|[A-Z][\w'\-]+|de|del|van|von|di|da)(?:\s+(?:[A-Z]\.|[A-Z][\w'\-]+|de|del|van|von|di|da))*)")


def sniff_director_year(synopsis_text: str) -> tuple[str | None, int | None]:
    director = None
    if m := DIRECTED_BY.search(synopsis_text):
        director = m.group(1).strip(" ,.")
    year = None
    if m := re.search(r"\((\d{4})\)|is an? (\d{4})\b|released in (\d{4})|the (\d{4}) adaptation", synopsis_text[:400]):
        year = int(next(g for g in m.groups() if g))
    return director, year


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def load_export(xml_path: Path) -> tuple[list[Review], dict[str, dict]]:
    channel = ET.parse(xml_path).getroot().find("channel")
    attachments: dict[str, dict] = {}
    reviews: list[Review] = []
    for item in channel.findall("item"):
        ptype = item.findtext("wp:post_type", namespaces=NS)
        pid = item.findtext("wp:post_id", namespaces=NS)
        if ptype == "attachment":
            attachments[pid] = {
                "url": item.findtext("wp:attachment_url", namespaces=NS),
                "parent": item.findtext("wp:post_parent", namespaces=NS),
            }
        elif ptype == "post" and item.findtext("wp:status", namespaces=NS) == "publish":
            meta = {m.findtext("wp:meta_key", namespaces=NS): m.findtext("wp:meta_value", namespaces=NS)
                    for m in item.findall("wp:postmeta", namespaces=NS)}
            reviews.append(Review(
                wp_id=pid,
                slug=item.findtext("wp:post_name", namespaces=NS),
                title=html.unescape(item.findtext("title") or "").strip(),
                post_date=item.findtext("wp:post_date", namespaces=NS),
                body=item.findtext("content:encoded", namespaces=NS) or "",
                thumbnail_id=meta.get("_thumbnail_id"),
                categories=[c.text for c in item.findall("category") if c.text],
            ))
    return reviews, attachments


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def image_ext(url: str) -> str:
    ext = Path(url.split("?")[0]).suffix.lower()
    return ".jpg" if ext == ".jpeg" else ext


def download(url: str, dest: Path) -> str:
    if dest.exists():
        return "exists"
    dest.parent.mkdir(parents=True, exist_ok=True)
    # The WordPress host blocks scripted requests (403); Jetpack's image CDN
    # mirrors the same originals, so fall back to it.
    candidates = [url, "https://i0.wp.com/" + re.sub(r"^https?://", "", url)]
    error = None
    for candidate in candidates:
        req = urllib.request.Request(candidate, headers={"User-Agent": "DAS-migration/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                if not resp.headers.get("Content-Type", "").startswith("image/"):
                    raise ValueError(f"not an image ({resp.headers.get('Content-Type')})")
                dest.write_bytes(resp.read())
            return "downloaded" if candidate == url else "downloaded via Jetpack CDN"
        except Exception as exc:  # noqa: BLE001 - try next source, then report
            error = exc
    return f"FAILED ({error})"


def render_markdown(r: Review, screened: str, score_key: str, display_title: str,
                    poster: str | None, banner: str | None) -> str:
    fm = [
        "---",
        f"title: {yaml_str(display_title)}",
        f"date: {screened}",
        f"score_key: {yaml_str(score_key)}",
        f"director: {yaml_str(r.director or '')}",
        f"year: {r.year or ''}".rstrip(),
        f"nominator: {yaml_str(r.nominator or '')}",
        f"nomination_month: {yaml_str(r.nomination_month or '')}",
        "nominations:",
    ]
    for n in r.nominations:
        fm.append(f"  - film: {yaml_str(n.film)}")
        if n.votes is not None:
            fm.append(f"    votes: {n.votes}")
        if n.nominated_by:
            fm.append(f"    nominated_by: {yaml_str(n.nominated_by)}")
        if n.winner:
            fm.append("    winner: true")
        if n.winner and n.tiebreak:
            fm.append("    tiebreak: true")
    fm += [
        f"poster: {yaml_str(poster or '')}",
        f"banner: {yaml_str(banner or '')}",
        f"aliases: [{yaml_str('/' + r.slug + '/')}]",
        f"wordpress_id: {r.wp_id}",
        "---",
        "",
    ]
    return "\n".join(fm) + r.synopsis_md


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="overwrite existing review files")
    ap.add_argument("--download-images", action="store_true", help="fetch posters/stills from WordPress")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    xml_files = sorted(MASTER.glob(XML_GLOB))
    if not xml_files:
        print(f"No WordPress export found in {MASTER / 'wordpress'}")
        return 1
    reviews, attachments = load_export(xml_files[-1])

    # Screening date + nominator per film, from the score ledger.
    ratings = read_csv(RATINGS_CSV)
    csv_films: dict[str, dict] = {}
    for row in ratings:
        d = datetime.strptime(row["date"], "%d/%m/%Y").date()
        info = csv_films.setdefault(row["movie"], {"date": d, "list_user": row["list_user"]})
        info["date"] = min(info["date"], d)
    users = read_csv(USERS_CSV)
    name_to_code = {u["full_name"]: u["user_code"] for u in users}
    known_codes = set(name_to_code.values())
    facts = {row["score_key"]: row for row in read_csv(FACTS_CSV)} if FACTS_CSV.exists() else {}

    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    written, skipped, image_log = [], [], []

    for r in reviews:
        pre, synopsis_html = split_sections(r.body)
        parse_nominator(pre, r)
        parse_nominations(pre, r)
        r.synopsis_md = html_to_markdown(synopsis_html)
        if not r.synopsis_md.strip():
            r.notes.append("empty synopsis")

        # Join to the score ledger.
        score_key = r.title
        if score_key not in csv_films:
            close = difflib.get_close_matches(score_key, csv_films, n=1, cutoff=0.85)
            if close:
                r.notes.append(f"title '{r.title}' matched ledger film '{close[0]}'")
                score_key = close[0]
            else:
                r.notes.append("NOT IN SCORE CSV — page will render without scores")
        ledger = csv_films.get(score_key)
        screened = (ledger["date"] if ledger else datetime.fromisoformat(r.post_date).date()).isoformat()

        if r.nominator and r.nominator not in known_codes:
            r.notes.append(f"nominator '{r.nominator}' is not in config_users.csv")
        if ledger and r.nominator:
            csv_code = name_to_code.get(ledger["list_user"])
            if csv_code and csv_code != r.nominator:
                r.notes.append(
                    f"nominator conflict: WordPress says {r.nominator}, score CSV list_user says "
                    f"{ledger['list_user']} ({csv_code}) — used WordPress")

        # Director / year: curated facts file wins; the synopsis is a cross-check.
        sniffed_dir, sniffed_year = sniff_director_year(strip_tags(synopsis_html))
        fact = facts.get(score_key, {})
        r.director = fact.get("director") or sniffed_dir
        r.year = int(fact["year"]) if fact.get("year") else sniffed_year
        if sniffed_dir and fact.get("director") and normalise(sniffed_dir) not in normalise(fact["director"]):
            r.notes.append(f"director: facts file '{fact['director']}' vs synopsis '{sniffed_dir}'")
        if sniffed_year and fact.get("year") and sniffed_year != int(fact["year"]):
            r.notes.append(f"year: facts file {fact['year']} vs synopsis {sniffed_year}")
        if not r.director:
            r.notes.append("director unknown — add to master-data/film_facts.csv")
        display_title = fact.get("display_title") or r.title

        # Media: featured image -> poster, any other attachments -> banner stills.
        poster = banner = None
        if r.thumbnail_id and r.thumbnail_id in attachments:
            url = attachments[r.thumbnail_id]["url"]
            poster = f"images/posters/{r.slug}{image_ext(url)}"
            if args.download_images:
                image_log.append((poster, download(url, IMAGES_DIR / poster.split("/", 1)[1])))
        else:
            r.notes.append("no featured image")
        extras = [a for aid, a in sorted(attachments.items(), key=lambda kv: int(kv[0]))
                  if a["parent"] == r.wp_id and aid != r.thumbnail_id]
        for i, a in enumerate(extras, start=1):
            path = f"images/banners/{r.slug}{'' if i == 1 else f'-{i}'}{image_ext(a['url'])}"
            dest = IMAGES_DIR / path.split("/", 1)[1]
            if args.download_images:
                status = download(a["url"], dest)
                poster_file = IMAGES_DIR / poster.split("/", 1)[1] if poster else None
                if dest.exists() and poster_file and poster_file.exists() \
                        and dest.read_bytes() == poster_file.read_bytes():
                    dest.unlink()
                    status = "skipped (identical to poster)"
                image_log.append((path, status))
            if dest.exists() or not args.download_images:
                banner = banner or path

        out = REVIEWS_DIR / f"{r.slug}.md"
        if out.exists() and not args.force:
            skipped.append(r)
            continue
        out.write_text(render_markdown(r, screened, score_key, display_title, poster, banner),
                       encoding="utf-8", newline="\n")
        written.append(r)

    # ---- Report -----------------------------------------------------------
    lines = [
        "# WordPress migration report",
        "",
        f"Source: `{xml_files[-1].name}` · generated {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"- Reviews written: **{len(written)}**",
        f"- Skipped (already exist, use --force): **{len(skipped)}**",
        f"- Films in score CSV with no review: "
        f"{', '.join(sorted(set(csv_films) - {r.title for r in reviews})) or 'none'}",
        "",
        "## Notes needing a human eye",
        "",
    ]
    noted = [r for r in reviews if r.notes]
    for r in noted:
        lines.append(f"### {r.title} (`content/reviews/{r.slug}.md`)")
        lines += [f"- {n}" for n in r.notes] + [""]
    if not noted:
        lines.append("None.")
    if image_log:
        lines += ["", "## Images", ""] + [f"- `{p}` — {s}" for p, s in image_log]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"Wrote {len(written)} reviews, skipped {len(skipped)} existing.")
    print(f"{len(noted)} reviews have notes — see {REPORT_PATH.relative_to(ROOT)}")
    if image_log:
        failed = [p for p, s in image_log if s.startswith("FAILED")]
        print(f"Images: {len(image_log) - len(failed)} ok, {len(failed)} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

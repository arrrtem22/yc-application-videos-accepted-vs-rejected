#!/usr/bin/env python3
"""Find more YC application videos on YouTube and guess each outcome.

Runs YouTube searches with yt-dlp, keeps videos whose title looks like a YC
application or founder video, and decides the outcome in this order:

  1. The title says rejected / not accepted / didn't get in  -> REJECTED (title)
  2. The title says accepted / got in                       -> ACCEPTED (title)
  3. A company in the YC directory (yc-oss) matches the title -> ACCEPTED (yc directory)
  4. The video is on the official Y Combinator channel       -> ACCEPTED (yc channel)
  5. The title names a batch the directory has, and no company
     from that batch is in the title                         -> LIKELY_REJECTED
  6. Otherwise                                               -> UNKNOWN

Rule 5 is a guess: a company that renamed or pivoted after the video also
lands here.

Rule 3 needs the company name as a whole word in the title, plus either the
same batch in the title or the title starting with the name.

Videos already in partnersim.csv are skipped.

Usage:
  python3 discover.py                 # writes discovered.csv + discovered.json
  python3 discover.py --per-query 200 # more results per search
"""
import argparse
import csv
import json
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
YC_DIRECTORY = "https://yc-oss.github.io/api/companies/all.json"

QUERIES = [
    "YC application video", "Y Combinator application video",
    "YC founder video", "Y Combinator founder video",
    "YC application video accepted", "YC application video rejected",
    "YC application video not accepted", "YC application rejected",
    "rejected from Y Combinator application video",
    "YC application video 2026", "YC application video 2025",
    "YC application video 2024", "YC application video 2023",
    "YC application video 2022", "YC application video 2021",
    "YC application video 2020", "YC application video 2019",
    "YC application video 2018", "YC application video 2017",
    "YC application video 2016", "YC application video 2015",
    "YC W26 application video", "YC S25 application video",
    "YC F25 application video", "YC X25 application video",
    "YC W25 application video", "YC F24 application video",
    "YC S24 application video", "YC W24 application video",
    "YC S23 application video", "YC W23 application video",
    "YC Spring 2026 application video",
    "Y Combinator application video for YC",
    "our YC application video", "my YC application video",
    "Y Combinator 1 minute founder video",
]

YC_WORD = re.compile(r"\b(yc|y\s?combinator|ycombinator)\b", re.I)
APP_WORD = re.compile(r"applica|founder video|\bvideo\b.*accepted|apply video|applied|submission", re.I)
NOT_AN_APP = re.compile(
    r"\btips?\b|how to|how i|how we|interview|advice|reading|react|review|guide|"
    r"mistakes|podcast|explained|\bwhy\b|secret|nail|webinar|office hours|"
    r"what yc|lessons|course|template|essay|questions|answers|roast|breakdown|"
    r"\bvs\b|watch me|rating|ranking|feedback|sues|walkthrough|\btop\s?\d|"
    r"\bhe\b|\bshe\b|news", re.I)
REJECTED = re.compile(r"reject|not accepted|didn'?t get in|did not get in|denied|"
                      r"turned down|\bfail", re.I)
ACCEPTED = re.compile(r"accepted|got in|got into", re.I)

SEASON = {"w": "Winter", "s": "Summer", "f": "Fall", "x": "Spring",
          "winter": "Winter", "summer": "Summer", "fall": "Fall", "spring": "Spring"}
BATCH_RE = re.compile(
    r"\b(winter|summer|fall|spring|[wsfx])\s?'?(?:20)?(\d{2})\b", re.I)


def title_batch(title: str) -> str:
    m = BATCH_RE.search(title)
    return f"{SEASON[m[1].lower()]} 20{m[2]}" if m else ""


def search(query: str, n: int) -> list[dict]:
    """One YouTube search. Retries, because parallel searches sometimes come back short."""
    best: list[dict] = []
    for _ in range(3):
        out = subprocess.run(["yt-dlp", "--flat-playlist", "-J", f"ytsearch{n}:{query}"],
                             capture_output=True, text=True)
        if out.returncode == 0:
            entries = json.loads(out.stdout).get("entries") or []
            if len(entries) > len(best):
                best = entries
            if len(best) >= n * 0.8:
                break
    print(f"{len(best):4} results  {query}", file=sys.stderr)
    return best


def load_directory() -> list[dict]:
    req = urllib.request.Request(YC_DIRECTORY, headers={"User-Agent": "Mozilla/5.0"})
    companies = json.loads(urllib.request.urlopen(req, timeout=60).read())
    for c in companies:
        c["_re"] = re.compile(r"(?<![\w])" + re.escape(c["name"]) + r"(?![\w])", re.I)
    skip = {"y combinator", "yc", "winter", "summer", "fall", "spring"}
    return [c for c in companies if len(c["name"]) >= 3 and c["name"].lower() not in skip]


def match_directory(title: str, companies: list[dict]) -> dict | None:
    batch = title_batch(title)
    best = None
    for c in companies:
        if not c["_re"].search(title):
            continue
        same_batch = batch and c.get("batch") == batch
        starts = title.lower().lstrip("[(accepted)] ").startswith(c["name"].lower())
        if same_batch or (not batch and starts):
            if best is None or len(c["name"]) > len(best["name"]):
                best = c
    if best or not batch:
        return best
    # Same batch, and the title's leading name is the start of a directory name:
    # "Cactus (YC S25)" -> "Cactus Compute", "Kater YC W24" -> "kater.ai".
    lead = re.split(r"\s[-|(—–:]|\(|'s\b|\s(?:yc|y\s?combinator)\b",
                    re.sub(r"^\W*(accepted|rejected)\W*", "", title, flags=re.I),
                    maxsplit=1, flags=re.I)[0]
    lead = norm(lead)
    if len(lead) < 4:
        return None
    for c in companies:
        if c.get("batch") == batch and norm(c["name"]).startswith(lead):
            return c
    return None


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def classify(e: dict, companies: list[dict], batches: set[str]) -> dict:
    title = e.get("title") or ""
    channel = e.get("channel") or ""
    row = {
        "decision": "UNKNOWN", "how_decided": "", "company": "", "batch": title_batch(title),
        "yc_status": "", "video_id": e["id"],
        "url": f"https://www.youtube.com/watch?v={e['id']}",
        "title": title, "channel": channel,
    }
    hit = match_directory(title, companies)
    if hit:
        row.update(company=hit["name"], batch=hit.get("batch", ""),
                   yc_status=hit.get("status", ""))
    if REJECTED.search(title):
        row.update(decision="REJECTED", how_decided="title")
    elif ACCEPTED.search(title):
        row.update(decision="ACCEPTED", how_decided="title")
    elif hit:
        row.update(decision="ACCEPTED", how_decided="yc directory")
    elif channel.lower() == "y combinator":
        row.update(decision="ACCEPTED", how_decided="yc channel")
    elif row["batch"] in batches:
        row.update(decision="LIKELY_REJECTED", how_decided="no such company in that batch")
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-query", type=int, default=100)
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args()

    known = set()
    known_csv = HERE / "partnersim.csv"
    if known_csv.exists():
        known = {r["video_id"] for r in csv.DictReader(open(known_csv))}

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda q: search(q, args.per_query), QUERIES))

    seen, candidates = set(), []
    for entries in results:
        for e in entries:
            vid, title = e.get("id"), e.get("title") or ""
            if not vid or vid in seen or vid in known:
                continue
            seen.add(vid)
            if YC_WORD.search(title) and APP_WORD.search(title) and not NOT_AN_APP.search(title):
                candidates.append(e)

    companies = load_directory()
    batches = {c.get("batch") for c in companies}
    rows = [classify(e, companies, batches) for e in candidates]
    rows.sort(key=lambda r: (r["decision"], r["batch"], r["title"].lower()))

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "discovered.json").write_text(json.dumps(rows, indent=2))
    with open(args.out / "discovered.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    counts = {d: sum(r["decision"] == d for r in rows) for d in ("ACCEPTED", "REJECTED", "LIKELY_REJECTED", "UNKNOWN")}
    print(f"{len(seen)} search results, {len(rows)} new application videos: {counts}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

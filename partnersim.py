#!/usr/bin/env python3
"""Dump YC Arena "Partner Sim" pitches: which company was accepted or rejected.

The game page loads its answer key from /assets/js/applications.js
(videoId, wasAccepted, companyName, batch, note). This script fetches that
file, writes partnersim.csv + partnersim.json, and can also pull each
YouTube video (and its subtitles) with yt-dlp.

Usage:
  python3 partnersim.py OUT_DIR              # CSV + JSON only
  python3 partnersim.py OUT_DIR --titles     # add YouTube title/channel/date
  python3 partnersim.py OUT_DIR --subs       # also download English subtitles
  python3 partnersim.py OUT_DIR --videos     # also download the mp4s
"""
import argparse
import csv
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

DATA_URL = "https://www.ycarena.com/assets/js/applications.js"
KEYS = ("videoId", "wasAccepted", "companyName", "batch", "note")


def fetch_applications() -> list[dict]:
    req = urllib.request.Request(DATA_URL, headers={"User-Agent": "Mozilla/5.0"})
    js = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    body = js[js.index("["): js.rindex("]") + 1]
    body = body.replace("!0", "true").replace("!1", "false")
    # Quote only the known keys, and only right after "{" or ",".
    body = re.sub(r"([{,])(%s):" % "|".join(KEYS), r'\1"\2":', body)
    body = re.sub(r",\s*([\]}])", r"\1", body)  # JS allows trailing commas
    return json.loads(body)


def batch_label(batch: str) -> str:
    m = re.match(r"([WSFX]?)(\d{2})$", batch or "")
    if not m:
        return batch or ""
    season = {"W": "Winter", "S": "Summer", "F": "Fall", "X": "Spring"}.get(m[1], "")
    return f"{season} 20{m[2]}".strip()


def yt_meta(video_id: str) -> dict:
    out = subprocess.run(
        ["yt-dlp", "-J", "--skip-download", f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return {"title": "", "channel": "", "upload_date": "", "duration": "",
                "yt_error": out.stderr.strip().splitlines()[-1] if out.stderr else "failed"}
    d = json.loads(out.stdout)
    return {"title": d.get("title", ""), "channel": d.get("channel", ""),
            "upload_date": d.get("upload_date", ""), "duration": d.get("duration", ""),
            "yt_error": ""}


def yt_download(video_id: str, out_dir: Path, video: bool, subs: bool) -> None:
    cmd = ["yt-dlp", "-o", str(out_dir / "%(id)s.%(ext)s"), "--no-overwrites"]
    if subs:
        cmd += ["--write-subs", "--write-auto-subs", "--sub-langs", "en.*",
                "--convert-subs", "srt"]
    if video:
        cmd += ["-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b", "--merge-output-format", "mp4"]
    else:
        cmd += ["--skip-download"]
    cmd.append(f"https://www.youtube.com/watch?v={video_id}")
    subprocess.run(cmd, check=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--titles", action="store_true", help="add YouTube metadata")
    ap.add_argument("--subs", action="store_true", help="download subtitles (srt)")
    ap.add_argument("--videos", action="store_true", help="download mp4s")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    apps = fetch_applications()
    rows = []
    for i, a in enumerate(apps, 1):
        row = {
            "n": i,
            "decision": "ACCEPTED" if a.get("wasAccepted") else "REJECTED",
            "company": a.get("companyName") or "(unnamed)",
            "batch": a.get("batch", ""),
            "batch_label": batch_label(a.get("batch", "")),
            "note": a.get("note", ""),
            "video_id": a["videoId"],
            "url": f"https://www.youtube.com/watch?v={a['videoId']}",
        }
        if args.titles:
            row.update(yt_meta(a["videoId"]))
        if args.subs or args.videos:
            yt_download(a["videoId"], args.out_dir / "media", args.videos, args.subs)
            srt = sorted((args.out_dir / "media").glob(f"{a['videoId']}*.srt"))
            row["subs_file"] = str(srt[0]) if srt else ""
        rows.append(row)
        print(f"{i:3}/{len(apps)} {row['decision']:8} {row['company']} ({row['batch']})",
              file=sys.stderr)

    (args.out_dir / "partnersim.json").write_text(json.dumps(rows, indent=2))
    with open(args.out_dir / "partnersim.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    acc = sum(r["decision"] == "ACCEPTED" for r in rows)
    print(f"\n{len(rows)} pitches: {acc} accepted, {len(rows) - acc} rejected", file=sys.stderr)
    print(f"wrote {args.out_dir / 'partnersim.csv'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

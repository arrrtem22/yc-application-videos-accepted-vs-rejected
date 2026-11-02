# YC application videos: accepted vs rejected

557 Y Combinator application videos (founder videos) from YouTube, each labeled accepted or rejected, as CSV and JSON. Use them as YC application video examples, or point an AI agent at the files and ask what the accepted videos have in common, which mistakes the rejected ones share, or how to structure your own video for YC or another startup accelerator.

Two lists, with the outcome for each.

## 1. YC Arena Partner Sim (102 videos, known answers)

[YC Partner Simulator](https://www.ycarena.com/games/partnersim) shows real YC application videos and asks if the startup got in. `partnersim.csv` / `partnersim.json` list the answer for all 102 videos: 24 accepted, 78 rejected. Columns: decision, company, batch, the site's note, YouTube link, video title, channel, upload date, length.

The answers come from the game's own data file, `https://www.ycarena.com/assets/js/applications.js`. Company names and notes are YC Arena's. They don't always match the video. Row 2 says "Reducto", but the video is "Remembrall YC Application (W24)", and the note says the company pivoted. Most rejected videos have no company name. 7 videos were private or deleted when this ran (`yt_error` column).

## 2. More videos found on YouTube (455 videos, guessed answers)

`discovered.csv` / `discovered.json` hold 455 more videos from 36 YouTube searches, with the YC Arena videos removed. Each row has a `decision` and a `how_decided` column:

| decision | count | how_decided |
|---|---|---|
| ACCEPTED | 20 | the title says accepted, or the company is in the [YC directory](https://github.com/yc-oss/api) for the batch in the title |
| REJECTED | 18 | the title says rejected, not accepted or denied |
| LIKELY_REJECTED | 291 | the title names a batch, and no company from that batch in the YC directory matches the title |
| UNKNOWN | 126 | no batch in the title and no directory match |

LIKELY_REJECTED is a guess. A company that renamed or pivoted after the video (like Reducto above) lands there too. Filtering titles also lets a few non-application videos through.

## Run

Needs Python 3.10+ and `yt-dlp` (only for the flags and for `discover.py`).

```
python3 partnersim.py out              # YC Arena list: CSV + JSON
python3 partnersim.py out --titles     # add YouTube title, channel, date
python3 partnersim.py out --subs       # download English subtitles (.srt)
python3 partnersim.py out --videos     # download the mp4s
python3 discover.py                    # search YouTube, write discovered.csv
python3 discover.py --per-query 200    # more results per search
```

Transcripts and videos aren't in the repo. They belong to the people who made the videos. Download them with the flags above.

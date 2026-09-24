"""Reachy's diary: what the robot saw today, for the people standing in front of it.

Reads the photos the glasses left in ``.runtime/glasses`` and the readings the
diary store kept, and serves them as one warm page on a local port. Nothing is
copied: the page links straight at the photos on disk.

Stdlib only, on purpose - this has to come up in under a second at a booth,
and it has nothing to do with the live robot processes.
"""

from __future__ import annotations

import os
import re
import sys
import json
import mimetypes
from pathlib import Path
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
STATIC = ROOT / "static"

sys.path.insert(0, str(ROOT))
import diary_store  # noqa: E402

PHOTOS = Path(os.getenv("REACHY_DIARY_PHOTOS") or PROJECT / ".runtime" / "glasses")
HOST = os.getenv("REACHY_DIARY_HOST", "127.0.0.1")
PORT = int(os.getenv("REACHY_DIARY_PORT", "8800"))

# glasses-20260924T060228Z.jpg, or ...Z-1.jpg when two land in the same second.
STAMPED = re.compile(r"^glasses-(\d{8}T\d{6}Z)(?:-(\d+))?\.jpg$", re.IGNORECASE)
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\.jpg$", re.IGNORECASE)

EMOTIONS = ("joy", "affection", "surprise", "curiosity",
            "sadness", "fear", "anger", "neutral")

# What Reachy says about a photo nobody read for it. Honest rather than
# invented: it did see something, it just has no words for this one. Picked by
# the photo's own name so a moment keeps the same line every time the page polls.
UNREAD_LINES = (
    ("光线有点暗，我只看见一团温柔的影子。",
     "The light was low. I only saw a soft shape."),
    ("我看见了，只是还没想好怎么说。",
     "I saw it. I just haven't found the words yet."),
    ("这一眼我记住了，句子还在路上。",
     "I kept this one. The sentence is still on its way."),
    ("当时我在看，来不及写下来。",
     "I was watching. I didn't get to write it down."),
    ("先把它收进口袋，晚点再讲给你听。",
     "Into my pocket for now. I'll tell you later."),
)


def _taken_at(photo: Path) -> datetime:
    """When the photo was taken, from its name; its mtime if the name is odd."""
    match = STAMPED.match(photo.name)
    if match:
        try:
            stamp = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
            return stamp.replace(tzinfo=timezone.utc).astimezone()
        except ValueError:
            pass
    return datetime.fromtimestamp(photo.stat().st_mtime).astimezone()


def _photos() -> list[Path]:
    if not PHOTOS.is_dir():
        return []
    return [p for p in PHOTOS.iterdir() if p.is_file() and p.suffix.lower() == ".jpg"]


def _moment(photo: Path, reading: dict | None) -> dict:
    """One diary entry, in the words the page will actually print."""
    taken = _taken_at(photo)
    moment = {
        "id": photo.stem,
        "photo": "/photo/" + photo.name,
        "time": taken.strftime("%H:%M"),
        "day": taken.strftime("%Y-%m-%d"),
        "sort": taken.timestamp(),
        "read": False,
        "emotion": "pending",
        "intensity": 0.35,
    }

    line_zh = (reading or {}).get("line_zh") or ""
    utterance = (reading or {}).get("utterance") or ""
    if reading and (line_zh or utterance):
        emotion = str(reading.get("emotion") or "neutral").lower()
        moment["read"] = True
        moment["emotion"] = emotion if emotion in EMOTIONS else "neutral"
        try:
            moment["intensity"] = max(0.0, min(1.0, float(reading.get("intensity", 0.5))))
        except (TypeError, ValueError):
            moment["intensity"] = 0.5
        moment["line"] = line_zh or utterance
        moment["aside"] = utterance if (line_zh and utterance) else ""
    else:
        line, aside = UNREAD_LINES[sum(photo.stem.encode()) % len(UNREAD_LINES)]
        moment["line"] = line
        moment["aside"] = aside
    return moment


def diary() -> dict:
    """Everything the page needs: the moments, and the mood of the latest day."""
    readings = diary_store.load()
    moments = sorted(
        (_moment(photo, readings.get(photo.stem)) for photo in _photos()),
        key=lambda m: m["sort"],
        reverse=True,
    )

    today = moments[0]["day"] if moments else datetime.now().astimezone().strftime("%Y-%m-%d")
    of_today = [m for m in moments if m["day"] == today]
    tally: dict[str, int] = {}
    for moment in of_today:
        if moment["read"]:
            tally[moment["emotion"]] = tally.get(moment["emotion"], 0) + 1

    mood = max(tally, key=lambda name: tally[name]) if tally else "pending"
    return {
        "day": today,
        "count": len(of_today),
        "total": len(moments),
        "mood": mood,
        "tally": tally,
        "read": sum(1 for m in of_today if m["read"]),
        "strip": [{"emotion": m["emotion"], "time": m["time"]} for m in reversed(of_today)],
        "moments": moments,
        # Changes whenever anything on the page would change, so the browser
        # can poll cheaply and only redraw when there is news.
        "stamp": str(hash(tuple((m["id"], m["emotion"], m.get("line")) for m in moments))),
    }


class Handler(SimpleHTTPRequestHandler):
    """Three things: the page, the diary JSON, and the photos themselves."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):  # one line per request is noise at a booth
        pass

    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/api/diary":
            return self._json(diary())
        if route.startswith("/photo/"):
            return self._photo(route[len("/photo/"):])
        if route in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _photo(self, name: str) -> None:
        if not SAFE_NAME.match(name):
            return self.send_error(404)
        target = (PHOTOS / name).resolve()
        try:
            target.relative_to(PHOTOS.resolve())
        except ValueError:
            return self.send_error(404)
        if not target.is_file():
            return self.send_error(404)
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(name)[0] or "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Reachy's diary on http://{HOST}:{PORT}", flush=True)
    print(f"photos: {PHOTOS}", flush=True)
    print(f"diary : {diary_store.path()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

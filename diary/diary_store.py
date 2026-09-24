"""The little book Reachy writes in.

A photo from the glasses is read once, acted out on the robot, and then the
reading is gone: nothing on disk remembers what Reachy felt. That is fine for
a reflex and useless for a diary, so this keeps one line per photo in a JSON
sidecar under ``data/`` (gitignored, it is the wearer's day).

The pipeline does not call this yet. One line is all it would take, right
after the reading comes back in ``bridge/glasses_pipeline.py``::

    from diary import diary_store
    diary_store.record(path, result)

``record`` never raises at the caller: a diary that fails to save must not
take a live robot down with it.
"""

from __future__ import annotations

import os
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = PROJECT / "data" / "diary.json"

# Only the keys the page actually shows, plus enough to sort and group. The
# rest of a reading (moves played, timings) belongs in the logs, not here.
KEPT = ("scene", "emotion", "intensity", "confidence", "utterance", "line_zh")

_lock = threading.Lock()


def path() -> Path:
    """Where the diary lives; overridable so tests never touch the real one."""
    return Path(os.getenv("REACHY_DIARY_PATH") or DEFAULT_PATH)


def entry_id(image: str | Path) -> str:
    """The photo's filename without its extension, e.g. glasses-2026...Z-1."""
    return Path(image).stem


def load() -> Dict[str, Any]:
    """Every reading written so far, keyed by photo id. Missing means empty."""
    target = path()
    try:
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except Exception as error:
        logger.warning("diary at %s unreadable (%s); starting from empty", target, error)
        return {}
    entries = data.get("entries") if isinstance(data, dict) else None
    return entries if isinstance(entries, dict) else {}


def record(image: str | Path, reading: Dict[str, Any]) -> bool:
    """Write one photo's reading into the diary. Returns whether it landed."""
    try:
        key = entry_id(image)
        entry = {name: reading.get(name) for name in KEPT if reading.get(name) is not None}
        entry["saved_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with _lock:
            entries = load()
            entries[key] = entry
            _write(entries)
        return True
    except Exception as error:  # a diary is never worth an outage
        logger.warning("could not write the diary entry for %s: %s", image, error)
        return False


def _write(entries: Dict[str, Any]) -> None:
    """Replace the file in one step, so a reader never sees a half-written diary."""
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    body = {"version": 1, "entries": entries}
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(body, handle, ensure_ascii=False, indent=1)
    os.replace(temporary, target)


if __name__ == "__main__":  # `... diary_store.py photo.jpg < reading.json`
    import sys

    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(0 if record(sys.argv[1], json.load(sys.stdin)) else 1)

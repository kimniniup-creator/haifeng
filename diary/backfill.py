"""Read photos that have no diary line yet, and write one for each.

The live pipeline reads a photo once and throws the reading away, so every
photo taken before the diary existed has no words. This walks the glasses
folder, asks the same vision stage the robot uses, and records the answer.

It only reads: no move is played and nothing the robot owns is touched.

    .venv\\Scripts\\python.exe diary\\backfill.py            # everything missing
    .venv\\Scripts\\python.exe diary\\backfill.py --limit 3  # just a few
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "diary"))

from dotenv import load_dotenv  # noqa: E402

import diary_store  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", default=str(PROJECT / ".runtime" / "glasses"))
    parser.add_argument("--limit", type=int, default=0, help="stop after this many")
    parser.add_argument("--again", action="store_true", help="re-read photos already written")
    args = parser.parse_args(argv)

    load_dotenv(PROJECT / ".env")
    from bridge.scene_agent import analyse  # after .env, it needs the credentials

    already = diary_store.load()
    photos = sorted(p for p in Path(args.photos).glob("*.jpg"))
    todo = [p for p in photos if args.again or p.stem not in already]
    if args.limit:
        todo = todo[-args.limit:]

    print(f"{len(photos)} photos, {len(todo)} to read")
    written = 0
    for photo in todo:
        try:
            reading = analyse(photo.read_bytes())
        except Exception as error:
            print(f"  {photo.name}: could not read it ({error})")
            continue
        diary_store.record(photo, reading)
        written += 1
        print(f"  {photo.name}: {reading['emotion']} {reading['intensity']:.2f} "
              f"| {reading['line_zh']} | {reading['utterance']}")
    print(f"wrote {written} into {diary_store.path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

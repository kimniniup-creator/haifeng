"""Keep the robot visibly alive between conversations.

A desk robot that only moves when spoken to reads as switched off. This plays a
short dance whenever nothing else is using the body, so it looks busy without
ever getting in the way: it only starts a move when the daemon reports the queue
empty, so a spoken reaction or an emotion always wins.

    .venv\\Scripts\\python.exe tools\\dance_keeper.py --min-gap 10 --max-gap 25
"""

import sys
import time
import json
import random
import argparse
import urllib.request
from typing import List, Optional, Sequence
from datetime import datetime

DAEMON = "http://127.0.0.1:8000"
DANCES = "pollen-robotics/reachy-mini-dances-library"

# Long, dizzying or floor-seeking moves are poor idle filler.
SKIP = {"dizzy_spin", "stumble_and_recover"}


def _get(path: str, timeout: float = 20.0):
    request = urllib.request.Request(DAEMON + path)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode() or "null")


def _post(path: str, timeout: float = 20.0):
    request = urllib.request.Request(DAEMON + path, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode() or "null")


def moves() -> List[str]:
    """The dance names the robot can actually play."""
    names = _get(f"/api/move/recorded-move-datasets/list/{DANCES}", timeout=60)
    return [n for n in names if n not in SKIP]


def busy() -> Optional[bool]:
    """True if a move is running, None when the robot cannot be reached."""
    try:
        status = _get("/api/daemon/status", timeout=8)
        if status.get("state") != "running" or status.get("error"):
            return None
        backend = status.get("backend_status") or {}
        if backend.get("motor_control_mode") != "enabled":
            # Torque is off: dancing would be silent and invisible.
            return None
        return bool(_get("/api/move/running", timeout=8))
    except Exception:
        return None


def main(argv: Sequence[str] | None = None) -> int:
    """Dance whenever the body is free, until interrupted."""
    parser = argparse.ArgumentParser(description="Idle dancing for the robot")
    parser.add_argument("--min-gap", type=float, default=10.0)
    parser.add_argument("--max-gap", type=float, default=25.0)
    parser.add_argument("--poll", type=float, default=2.0)
    args = parser.parse_args(argv)

    try:
        catalogue = moves()
    except Exception as error:
        print(f"cannot read the dance library: {error}", flush=True)
        return 1
    print(f"{len(catalogue)} dances available", flush=True)

    next_at = 0.0
    recent: List[str] = []

    while True:
        time.sleep(args.poll)
        state = busy()
        if state is None or state:
            # Unreachable, torque off, or something else is moving: wait.
            continue
        if time.time() < next_at:
            continue

        # Avoid repeating the last few, so it does not look like a loop.
        choices = [m for m in catalogue if m not in recent] or catalogue
        move = random.choice(choices)
        recent = (recent + [move])[-4:]
        try:
            _post(f"/api/move/play/recorded-move-dataset/{DANCES}/{move}")
            print(f"[{datetime.now():%H:%M:%S}] {move}", flush=True)
        except Exception as error:
            print(f"[{datetime.now():%H:%M:%S}] {move} failed: {error}", flush=True)
        next_at = time.time() + random.uniform(args.min_gap, args.max_gap)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)

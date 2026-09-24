"""Restart the conversation app when its realtime session goes quiet.

The hosted realtime session stops producing responses after a few minutes:
transcripts keep arriving, the websocket stays open, nothing is logged as an
error, and the robot simply never answers again. Observed lifetime was 4m57s.

There is no signal to wait on, so this watches the app's own log: if the user
was heard and no reply followed within `--grace` seconds, the session is
considered dead and the app is restarted. Silence alone is never enough - a
quiet room must not trigger a restart.
"""

import re
import sys
import time
import argparse
import subprocess
from typing import Optional, Sequence
from pathlib import Path
from datetime import datetime

ROOT = Path(r"D:\海风")
LOG = ROOT / ".runtime" / "conversation.stderr.log"
PID_FILE = ROOT / ".runtime" / "conversation.pid"
LAUNCHER = ROOT / "start_conversation.ps1"

# Lines that prove each side is alive. A partial transcript is not proof the
# user finished a turn, so only committed ones count.
USER_LINE = re.compile(r"role=user content=")
ALIVE_LINE = re.compile(r"role=assistant|Turn latency|Tool call received")
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _stamp(line: str) -> Optional[float]:
    match = STAMP.match(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def scan(path: Path, tail_bytes: int = 400_000) -> tuple[Optional[float], Optional[float]]:
    """Return (last user turn, last sign of life) as timestamps."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - tail_bytes))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None, None

    last_user = last_alive = None
    for line in text.splitlines():
        when = _stamp(line)
        if when is None:
            continue
        if USER_LINE.search(line):
            last_user = when
        if ALIVE_LINE.search(line):
            last_alive = when
    return last_user, last_alive


def restart() -> bool:
    """Stop the app and start it again through its own launcher."""
    try:
        pid = int(PID_FILE.read_text().strip())
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
            check=False, capture_output=True, timeout=30,
        )
    except (OSError, ValueError):
        pass
    time.sleep(3)
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER)],
        check=False, capture_output=True, text=True, timeout=120,
    )
    ok = result.returncode == 0
    print(f"  restart {'ok' if ok else 'FAILED'}: {(result.stdout or result.stderr).strip()[:160]}",
          flush=True)
    return ok


def main(argv: Sequence[str] | None = None) -> int:
    """Watch the log and restart a dead session until interrupted."""
    parser = argparse.ArgumentParser(description="Keep the conversation session alive")
    parser.add_argument("--grace", type=float, default=30.0,
                        help="seconds a heard user may go unanswered before restarting")
    parser.add_argument("--poll", type=float, default=5.0)
    parser.add_argument("--cooldown", type=float, default=90.0,
                        help="minimum seconds between restarts")
    args = parser.parse_args(argv)

    print(f"watching {LOG}", flush=True)
    print(f"restart when a heard user goes {args.grace:.0f}s unanswered", flush=True)
    last_restart = 0.0

    while True:
        time.sleep(args.poll)
        last_user, last_alive = scan(LOG)
        if last_user is None:
            continue

        answered = last_alive is not None and last_alive >= last_user
        unanswered_for = time.time() - last_user
        if answered or unanswered_for < args.grace:
            continue
        if time.time() - last_restart < args.cooldown:
            continue

        print(f"[{datetime.now():%H:%M:%S}] user unanswered for {unanswered_for:.0f}s "
              f"- session looks dead, restarting", flush=True)
        restart()
        last_restart = time.time()
        # Give the new session time to announce itself before judging it again.
        time.sleep(20)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)

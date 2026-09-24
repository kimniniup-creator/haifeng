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
# Proof we are actually sending audio upstream right now.
SENDING_LINE = re.compile(r"opening uplink|open=True")
# Any sign the relay is still processing what we send. Partial transcripts count:
# they arrive long before a turn completes, so their absence means it went deaf.
RELAY_LINE = re.compile(r"role=user|role=assistant|Turn latency")
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

# Survives across ticks without threading it through every signature.
_state = {"memory_mark": 0}

DAEMON = "http://127.0.0.1:8000"
MEMORY = ROOT / "conv-env" / "Lib" / "site-packages" / "reachy_mini_conversation_app" / "memory.v1.json"
REPLY_LINE = re.compile(r"role=assistant content=")


def _stamp(line: str) -> Optional[float]:
    match = STAMP.match(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def scan(path: Path, tail_bytes: int = 400_000) -> tuple[Optional[float], ...]:
    """Return timestamps for (last user turn, last reply, last send, last relay sign)."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - tail_bytes))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None, None, None, None

    last_user = last_alive = last_send = last_relay = None
    for line in text.splitlines():
        when = _stamp(line)
        if when is None:
            continue
        if USER_LINE.search(line):
            last_user = when
        if ALIVE_LINE.search(line):
            last_alive = when
        if SENDING_LINE.search(line):
            last_send = when
        if RELAY_LINE.search(line):
            last_relay = when
    return last_user, last_alive, last_send, last_relay


def clear_memory() -> int:
    """Drop stored facts so long sessions cannot accumulate stale memory."""
    import json

    try:
        data = json.loads(MEMORY.read_text(encoding="utf-8"))
        count = len(data.get("facts", []))
        if not count:
            return 0
        MEMORY.write_text(
            json.dumps({"version": 1, "facts": []}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return count
    except (OSError, ValueError):
        return 0


def count_replies(path: Path, tail_bytes: int = 400_000) -> int:
    """How many assistant turns the current log holds."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - tail_bytes))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return 0
    return sum(1 for line in text.splitlines() if REPLY_LINE.search(line))


def daemon_state() -> Optional[str]:
    """The robot daemon's own view of itself, or None when unreachable."""
    import json
    import urllib.request

    try:
        request = urllib.request.Request(f"{DAEMON}/api/daemon/status")
        with urllib.request.urlopen(request, timeout=5) as response:
            return str(json.loads(response.read().decode()).get("state"))
    except Exception:
        return None


def revive_daemon() -> bool:
    """Bring the robot backend out of an error state and re-enable the motors.

    A Reachy power-cycle leaves the daemon in `error` with a motor
    communication fault; the conversation app then floods with "Lost connection"
    and answers nobody. Restarting the backend is the documented recovery and
    does not touch firmware or calibration.
    """
    import urllib.request

    def post(path: str) -> bool:
        try:
            request = urllib.request.Request(DAEMON + path, data=b"", method="POST")
            with urllib.request.urlopen(request, timeout=30):
                return True
        except Exception as error:
            print(f"  POST {path} failed: {error}", flush=True)
            return False

    if not post("/api/daemon/restart"):
        return False
    for _ in range(12):
        time.sleep(3)
        if daemon_state() == "running":
            post("/api/motors/set_mode/enabled")
            print("  daemon recovered, motors enabled", flush=True)
            return True
    print("  daemon did not come back to running", flush=True)
    return False


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
    # Never capture the launcher's output: it uses Start-Process, whose detached
    # child inherits the pipe, so communicate() waits for an EOF that never
    # comes and the watchdog kills itself on the timeout.
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER)],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90,
        )
        ok = result.returncode == 0
    except subprocess.TimeoutExpired:
        # The launcher spawns and returns; a timeout here means it is still
        # holding the console, not that the app failed to start.
        ok = True
    except Exception as error:
        print(f"  restart failed: {error}", flush=True)
        return False
    print(f"  restart {'ok' if ok else 'returned non-zero'}", flush=True)
    return ok


def main(argv: Sequence[str] | None = None) -> int:
    """Watch the log and restart a dead session until interrupted."""
    parser = argparse.ArgumentParser(description="Keep the conversation session alive")
    parser.add_argument("--grace", type=float, default=30.0,
                        help="seconds a heard user may go unanswered before restarting")
    parser.add_argument("--poll", type=float, default=5.0)
    parser.add_argument("--cooldown", type=float, default=90.0,
                        help="minimum seconds between restarts")
    parser.add_argument("--memory-turns", type=int, default=20,
                        help="clear stored memory facts every N assistant turns; 0 disables")
    parser.add_argument("--deaf-grace", type=float, default=60.0,
                        help="seconds of streaming audio with no relay activity at all")
    args = parser.parse_args(argv)

    print(f"watching {LOG}", flush=True)
    print(f"restart when a heard user goes {args.grace:.0f}s unanswered", flush=True)
    last_restart = 0.0

    last_daemon_fix = 0.0

    while True:
        time.sleep(args.poll)
        try:
            last_restart, last_daemon_fix = _tick(args, last_restart, last_daemon_fix)
        except Exception as error:
            # The watchdog is the safety net; it must outlive any single failure.
            print(f"[{datetime.now():%H:%M:%S}] tick failed: {error!r}", flush=True)


def _tick(args, last_restart: float, last_daemon_fix: float) -> tuple[float, float]:
    """One check round. Returns the updated restart timestamps."""
    # The robot backend first: a dead daemon makes the app look deaf, and
    # restarting the app would not help.
    state = daemon_state()
    if state == "error" and time.time() - last_daemon_fix > args.cooldown:
        print(f"[{datetime.now():%H:%M:%S}] daemon in error state - reviving", flush=True)
        if revive_daemon():
            restart()
        last_daemon_fix = time.time()
        time.sleep(20)
        return last_restart, last_daemon_fix

    # Memory is deliberately short-lived: refresh it every so many turns so a
    # long session never carries stale facts forward.
    turns = count_replies(LOG)
    if args.memory_turns > 0 and turns - _state["memory_mark"] >= args.memory_turns:
        dropped = clear_memory()
        _state["memory_mark"] = turns
        if dropped:
            print(f"[{datetime.now():%H:%M:%S}] {turns} turns - cleared {dropped} memory facts",
                  flush=True)

    last_user, last_alive, last_send, last_relay = scan(LOG)

    # Deaf session: we are streaming audio upstream and getting nothing
    # back at all - not even a partial transcript. The heard-but-unanswered
    # check below cannot see this, because no transcript ever arrives.
    if (
        last_send is not None
        and time.time() - last_send < args.deaf_grace
        and (last_relay is None or time.time() - last_relay > args.deaf_grace)
        and time.time() - last_restart > args.cooldown
    ):
        quiet = time.time() - last_relay if last_relay else float("inf")
        print(f"[{datetime.now():%H:%M:%S}] sending audio but relay silent for "
              f"{quiet:.0f}s - restarting", flush=True)
        restart()
        last_restart = time.time()
        time.sleep(20)
        return last_restart, last_daemon_fix

    if last_user is None:
        return last_restart, last_daemon_fix

    answered = last_alive is not None and last_alive >= last_user
    unanswered_for = time.time() - last_user
    if answered or unanswered_for < args.grace:
        return last_restart, last_daemon_fix
    if time.time() - last_restart < args.cooldown:
        return last_restart, last_daemon_fix

    print(f"[{datetime.now():%H:%M:%S}] user unanswered for {unanswered_for:.0f}s "
          f"- session looks dead, restarting", flush=True)
    restart()
    last_restart = time.time()
    # Give the new session time to announce itself before judging it again.
    time.sleep(20)
    return last_restart, last_daemon_fix


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)

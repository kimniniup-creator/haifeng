"""Bring the robot backend back after a motor communication fault.

The Reachy Mini's whole USB tree - CH343 motor serial port, camera and audio -
hangs off one internal hub, and that hub drops off the bus on its own (Windows
logs it as a surprise removal in Kernel-PnP/Device Management). The motor
control loop then reads nothing.

The SDK gives that almost no slack. The Rust control loop retries a position
read `allowed_retries=5` times and then raises "Motor communication error!
Check connections and power supply."; the Python loop tolerates those only
while some iteration succeeded within the last second. Past that it re-raises,
and `backend_wrapped_run` sets state=error, stops the websocket server and
drops the backend to None. Nothing ever puts it back - every SDK client just
sees "Lost connection with the server." until a human restarts the backend.

So this is the missing half: watch for the fault and run the documented
recovery, with a cooldown and backoff so a robot that is genuinely unplugged
cannot be restart-thrashed.

Scope is deliberately narrow. Only four documented REST endpoints are ever
called (see ENDPOINTS); firmware, calibration and motor limits are never
touched. The conversation app is somebody else's job - tools/conversation_watchdog.py
owns that, and this guard leaves it alone.
"""

import sys
import json
import time
import argparse
import urllib.error
import urllib.request
from typing import Any, Optional, Sequence
from pathlib import Path
from datetime import datetime

DAEMON = "http://127.0.0.1:8000"
LOG = Path(r"D:\海风") / ".runtime" / "robot_guard.log"

# The complete set of endpoints this tool is allowed to touch. Everything here
# is read-only or a documented lifecycle call.
ENDPOINTS = (
    "GET  /api/daemon/status",
    "POST /api/daemon/restart",
    "POST /api/daemon/start?wake_up=false",
    "POST /api/motors/set_mode/enabled",
)

# HTTP_PROXY is set on this machine and would otherwise be applied to
# 127.0.0.1, which fails in a way that looks like the daemon is down.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_counters = {"faults": 0, "recovered": 0, "failed": 0}


def log(message: str, path: Path) -> None:
    """Print a stamped line and append it to the guard log."""
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
    print(line, flush=True)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass  # Losing the log must never stop the guard from recovering the robot.


def get_status() -> Optional[dict[str, Any]]:
    """The daemon's own view of itself, or None when it is unreachable."""
    try:
        with OPENER.open(f"{DAEMON}/api/daemon/status", timeout=5) as response:
            return dict(json.loads(response.read().decode()))
    except Exception:
        return None


def post(path: str, timeout: float = 30.0) -> bool:
    """Fire one documented POST. Returns whether the daemon accepted it."""
    request = urllib.request.Request(DAEMON + path, data=b"", method="POST")
    try:
        with OPENER.open(request, timeout=timeout):
            return True
    except Exception:
        return False


def describe(status: Optional[dict[str, Any]]) -> str:
    """One-line summary of a status payload, for the log."""
    if status is None:
        return "unreachable"
    backend = status.get("backend_status") or {}
    stats = backend.get("control_loop_stats") or {}
    return (
        f"state={status.get('state')} error={status.get('error')!r} "
        f"ready={backend.get('ready')} mode={backend.get('motor_control_mode')} "
        f"nb_error={stats.get('nb_error')} hz={stats.get('mean_control_loop_frequency')}"
    )


# A restart is a background job: for a moment the daemon still reports whatever
# it was before. Nothing it says inside this window is evidence either way.
SETTLE = 4.0


def wait_for_running(deadline: float, path: Path) -> bool:
    """Poll until the daemon reports running, or the deadline passes.

    `error` only counts once the restart has had SETTLE seconds to take hold -
    reading it immediately would abort a recovery that had not started yet.
    """
    time.sleep(SETTLE)
    began = time.time()
    while time.time() < deadline:
        status = get_status()
        if status is not None:
            state = status.get("state")
            if state == "running":
                return True
            if state == "error" and time.time() - began > SETTLE:
                # Straight back into error means the serial port is still gone;
                # no point burning the rest of the window on it.
                log(f"  still in error during restart: {status.get('error')!r}", path)
                return False
        time.sleep(2.0)
    return False


def recover(status: dict[str, Any], path: Path, wait: float) -> bool:
    """Run the documented recovery and confirm it actually took.

    error   -> /api/daemon/restart
    stopped -> /api/daemon/start?wake_up=false  (same call start_robot.ps1 makes)

    Either way the motors come back disabled, so they are re-enabled and the
    result is verified rather than assumed.
    """
    state = status.get("state")
    began = time.time()

    if state == "stopped":
        log("  recovery: /api/daemon/start?wake_up=false", path)
        accepted = post("/api/daemon/start?wake_up=false")
    else:
        log("  recovery: /api/daemon/restart", path)
        accepted = post("/api/daemon/restart")

    if not accepted:
        log("  the daemon refused the lifecycle call", path)
        return False

    if not wait_for_running(began + wait, path):
        log(f"  never reached running within {wait:.0f}s", path)
        return False

    if not post("/api/motors/set_mode/enabled"):
        log("  reached running but motors would not enable", path)
        return False

    after = get_status()
    backend = (after or {}).get("backend_status") or {}
    healthy = (
        after is not None
        and after.get("state") == "running"
        and after.get("error") is None
        and backend.get("ready") is True
        and backend.get("motor_control_mode") == "enabled"
    )
    log(f"  after {time.time() - began:.1f}s: {describe(after)}", path)
    return healthy


def _tick(args: argparse.Namespace, last_attempt: float, backoff: float) -> tuple[float, float]:
    """One check round. Returns the updated attempt time and backoff."""
    status = get_status()
    path = Path(args.log)

    if status is None:
        # No process is listening. Restarting requires launching the daemon,
        # which is outside this tool's remit, so say so and keep watching.
        _counters["faults"] += 1
        log("FAULT daemon unreachable on 127.0.0.1:8000 - "
            "start it with start_robot_media.ps1; the guard cannot do this itself", path)
        return last_attempt, backoff

    state = status.get("state")
    if state not in ("error", "stopped"):
        # A run of clean ticks means the last recovery held, so stop backing off.
        return last_attempt, args.cooldown

    _counters["faults"] += 1
    log(f"FAULT {describe(status)}", path)

    waited = time.time() - last_attempt
    if waited < backoff:
        log(f"  holding off {backoff - waited:.0f}s more (backoff {backoff:.0f}s)", path)
        return last_attempt, backoff

    if recover(status, path, args.wait):
        _counters["recovered"] += 1
        log(f"RECOVERED faults={_counters['faults']} recovered={_counters['recovered']} "
            f"failed={_counters['failed']}", path)
        # Settle before judging the robot again, so one fault is not counted twice.
        time.sleep(args.settle)
        return time.time(), args.cooldown

    _counters["failed"] += 1
    backoff = min(backoff * 2, args.max_backoff)
    log(f"RECOVERY FAILED faults={_counters['faults']} recovered={_counters['recovered']} "
        f"failed={_counters['failed']} - next attempt in {backoff:.0f}s", path)
    return time.time(), backoff


def main(argv: Sequence[str] | None = None) -> int:
    """Watch the daemon and recover it until interrupted."""
    parser = argparse.ArgumentParser(description="Keep the robot backend alive")
    parser.add_argument("--poll", type=float, default=5.0)
    parser.add_argument("--cooldown", type=float, default=60.0,
                        help="minimum seconds between recovery attempts")
    parser.add_argument("--max-backoff", type=float, default=600.0,
                        help="ceiling for the backoff after repeated failures")
    parser.add_argument("--wait", type=float, default=45.0,
                        help="seconds to wait for the daemon to report running")
    parser.add_argument("--settle", type=float, default=15.0,
                        help="seconds to leave a freshly recovered robot alone")
    parser.add_argument("--log", default=str(LOG))
    parser.add_argument("--once", action="store_true",
                        help="check once and exit; useful for a pre-demo smoke test")
    args = parser.parse_args(argv)

    path = Path(args.log)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    log(f"guarding {DAEMON} | endpoints: {', '.join(ENDPOINTS)}", path)
    log(f"startup state: {describe(get_status())}", path)

    if args.once:
        return 0

    last_attempt = 0.0
    backoff = args.cooldown
    while True:
        time.sleep(args.poll)
        try:
            last_attempt, backoff = _tick(args, last_attempt, backoff)
        except Exception as error:
            # The guard is the safety net; it has to outlive any single failure.
            log(f"tick failed: {error!r}", path)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)

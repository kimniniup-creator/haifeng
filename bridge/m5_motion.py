"""Shake the M5 and Reachy shakes its head with it.

    M5 IMU ──m5_motion──> this process ──goto──> Reachy head

Side to side on the stick is a head shake, up and down is a nod, a twist is a
roll wobble; tilting the stick and holding it gives one curious head tilt to
that side. Each gesture is a short chain of daemon `goto` moves: while one runs
the daemon ignores the conversation app's streamed targets, so the gesture is
not fought, and the app takes the head back when it ends.
"""

import os
import json
import math
import time
import logging
import threading
import urllib.request
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

DAEMON = os.getenv("REACHY_DAEMON_URL", "http://127.0.0.1:8000")
# Which way Reachy tilts for a stick leaning "right". Reachy faces the person,
# so mirroring what they see means the opposite of its own right.
TILT_SIGN = float(os.getenv("M5_TILT_SIGN", "-1"))

# axis -> which head angle swings: stick side-to-side = "no", up-down = nod.
SHAKE_ANGLE = {"x": "yaw", "y": "pitch", "z": "roll"}


def _call(method: str, path: str, body: Dict[str, Any] | None = None, timeout: float = 8.0) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        DAEMON + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode() or "null"
        return json.loads(text)


def shake_keyframes(axis: str, strength: float) -> List[Tuple[Dict[str, float], float]]:
    """(offset, seconds) steps for one shake: three swings that die away."""
    angle = SHAKE_ANGLE.get(axis, "yaw")
    # Big enough to see from across the desk; well inside the head's range.
    peak = math.radians(18 + 12 * min(max(strength, 0.0), 1.0))
    if angle == "pitch":
        peak *= 0.7  # nodding reads bigger than turning
    elif angle == "roll":
        peak *= 0.8
    steps = []
    for i, scale in enumerate((1.0, -1.0, 0.8, -0.6, 0.35)):
        steps.append(({angle: peak * scale}, 0.18 if i else 0.14))
    steps.append(({}, 0.2))
    return steps


def tilt_keyframes(side: str) -> List[Tuple[Dict[str, float], float]]:
    """A curious head tilt toward the side the stick leans, then back."""
    if side not in ("left", "right"):
        return []
    roll = math.radians(16) * TILT_SIGN * (1 if side == "right" else -1)
    return [({"roll": roll}, 0.35), ({"roll": roll * 1.05, "pitch": math.radians(-4)}, 0.7), ({}, 0.4)]


class ReachyMirror:
    """Plays M5 gestures on Reachy one at a time.

    One gesture waits while another plays. A shake always takes that slot, and
    tilts that arrive around a shake are ignored: shaking rocks the tilt
    reading both ways, and a head tilt must not stand in for the head shake.
    """

    SHAKE_HOLD_S = 1.5

    def __init__(self) -> None:
        self.pending: Dict[str, Any] | None = None
        self.ready = threading.Condition()
        self.last_shake = 0.0
        self.played = 0
        self.last: Dict[str, Any] = {}
        threading.Thread(target=self._work, daemon=True).start()

    def handle(self, message: Dict[str, Any]) -> None:
        """M5Link listener: take m5_motion events, ignore everything else."""
        if message.get("type") != "m5_motion":
            return
        with self.ready:
            if message.get("gesture") == "shake":
                self.last_shake = time.monotonic()
            elif time.monotonic() - self.last_shake < self.SHAKE_HOLD_S or (
                self.pending is not None and self.pending.get("gesture") == "shake"
            ):
                logger.info("tilt ignored during a shake")
                return
            if self.pending is not None:
                logger.info("replacing waiting %s", self.pending.get("gesture"))
            self.pending = message
            self.ready.notify()

    def _work(self) -> None:
        while True:
            with self.ready:
                while self.pending is None:
                    self.ready.wait()
                message, self.pending = self.pending, None
            try:
                self.play(message)
            except Exception as error:
                logger.warning("mirror failed: %s", error)

    def play(self, message: Dict[str, Any]) -> Dict[str, Any]:
        gesture = message.get("gesture")
        if gesture == "shake":
            frames = shake_keyframes(str(message.get("axis", "x")), float(message.get("strength", 0.5)))
        elif gesture == "tilt":
            frames = tilt_keyframes(str(message.get("side", "")))
        else:
            return {}
        if not frames:
            return {}
        started = time.time()
        if not self._wait_idle(1.5):
            logger.info("another move is playing; skipped %s", gesture)
            return {"skipped": True}
        base = _call("GET", "/api/state/present_head_pose?use_pose_matrix=false")
        sent = 0
        for offset, seconds in frames:
            pose = {key: base.get(key, 0.0) for key in ("x", "y", "z")}
            for key in ("roll", "pitch", "yaw"):
                pose[key] = base.get(key, 0.0) + offset.get(key, 0.0)
            _call("POST", "/api/move/goto", {"head_pose": pose, "duration": seconds})
            sent += 1
            time.sleep(seconds)
            self._wait_idle(0.5)
        self.played += 1
        self.last = {"gesture": gesture, "axis": message.get("axis"), "side": message.get("side"),
                     "moves": sent, "seconds": round(time.time() - started, 2),
                     "injected": bool(message.get("injected"))}
        logger.info("mirrored on Reachy: %s", self.last)
        return self.last

    @staticmethod
    def _wait_idle(timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not _call("GET", "/api/move/running"):
                return True
            time.sleep(0.02)
        return False


def main() -> int:
    """Mirror M5 shakes on Reachy without the glasses: `python -m bridge.m5_motion`."""
    import sys
    from bridge.m5_link import M5Link

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    link = M5Link(os.getenv("M5_PORT") or None)
    mirror = ReachyMirror()
    link.listeners.append(mirror.handle)
    link.listeners.append(lambda m: m.get("type") == "m5_motion" and logger.info("M5 says: %s", m))
    if not link.connect():
        print("M5 not found", file=sys.stderr)
        return 1
    print("Mirroring M5 shakes on Reachy. Ctrl+C to stop.", flush=True)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

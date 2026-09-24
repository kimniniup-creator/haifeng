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
import queue
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


def _call(method: str, path: str, body: Dict[str, Any] | None = None, timeout: float = 3.0) -> Any:
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
    peak = math.radians(12 + 14 * min(max(strength, 0.0), 1.0))
    if angle == "pitch":
        peak *= 0.7  # nodding reads bigger than turning
    steps = []
    for i, scale in enumerate((1.0, -0.85, 0.65, -0.45, 0.25)):
        steps.append(({angle: peak * scale}, 0.16 if i else 0.12))
    steps.append(({}, 0.2))
    return steps


def tilt_keyframes(side: str) -> List[Tuple[Dict[str, float], float]]:
    """A curious head tilt toward the side the stick leans, then back."""
    if side not in ("left", "right"):
        return []
    roll = math.radians(16) * TILT_SIGN * (1 if side == "right" else -1)
    return [({"roll": roll}, 0.35), ({"roll": roll * 1.05, "pitch": math.radians(-4)}, 0.7), ({}, 0.4)]


class ReachyMirror:
    """Plays M5 gestures on Reachy one at a time; extra gestures while busy are dropped."""

    def __init__(self) -> None:
        self.jobs: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=1)
        self.played = 0
        self.last: Dict[str, Any] = {}
        threading.Thread(target=self._work, daemon=True).start()

    def handle(self, message: Dict[str, Any]) -> None:
        """M5Link listener: take m5_motion events, ignore everything else."""
        if message.get("type") != "m5_motion":
            return
        try:
            self.jobs.put_nowait(message)
        except queue.Full:
            logger.info("Reachy still moving; dropped %s", message.get("gesture"))

    def _work(self) -> None:
        while True:
            message = self.jobs.get()
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

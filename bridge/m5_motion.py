"""Whatever the M5 character does, Reachy does too.

    M5 buttons / IMU ──m5_action──> this process ──goto / recorded move──> Reachy

The M5 decides what the person did (a nod, a head shake, a poke, a pat, the
side button's question...) and animates it; it sends the same action name
here, and Reachy acts it out. Quick gestures are short chains of daemon `goto`
moves so they keep pace with the stick; bigger feelings reuse the photo
emotion table so a laugh on the stick and a laugh at a photo look alike.

While a daemon move runs, it ignores the conversation app's streamed targets,
so a gesture is not fought; the app takes the head back when it ends.
"""

import os
import json
import math
import time
import random
import logging
import threading
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DAEMON = os.getenv("REACHY_DAEMON_URL", "http://127.0.0.1:8000")
# Which way Reachy tilts for a stick leaning "right". Reachy faces the person,
# so mirroring what they see means the opposite of its own right.
TILT_SIGN = float(os.getenv("M5_TILT_SIGN", "-1"))
# Recorded moves bring their own sound; off unless asked for.
WITH_SOUND = os.getenv("M5_MIRROR_SOUND", "0") == "1"

Frame = Tuple[Dict[str, float], Optional[Tuple[float, float]], float]  # head offset, antennas offset, seconds
DEG = math.radians


def _call(method: str, path: str, body: Dict[str, Any] | None = None, timeout: float = 8.0) -> Any:
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    request = urllib.request.Request(
        DAEMON + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode() or "null"
        return json.loads(text)


def swing(angle: str, peak: float, beats: Tuple[float, ...] = (1.0, -1.0, 0.8, -0.6, 0.35), beat: float = 0.18) -> List[Frame]:
    """Back-and-forth on one head angle that dies away, ending centred."""
    frames: List[Frame] = [({angle: peak * scale}, None, beat if i else beat * 0.8) for i, scale in enumerate(beats)]
    frames.append(({}, None, 0.2))
    return frames


def gesture_frames(action: str, strength: float = 0.7) -> List[Frame]:
    """Keyframes for the quick, goto-driven actions; empty if the action is not one."""
    s = min(max(strength, 0.0), 1.0)
    if action == "no":
        return swing("yaw", DEG(18 + 12 * s))
    if action == "yes":
        return swing("pitch", DEG(12 + 8 * s), beats=(1.0, -0.4, 1.0, -0.4, 0.6), beat=0.2)
    if action == "dizzy":
        a = DEG(12)
        circle = [({"roll": a}, None, 0.18), ({"pitch": a}, None, 0.18), ({"roll": -a}, None, 0.18), ({"pitch": -a}, None, 0.18)]
        return circle * 2 + [({}, (0.0, 0.0), 0.3)]
    if action in ("tilt_left", "tilt_right"):
        roll = DEG(16) * TILT_SIGN * (1 if action == "tilt_right" else -1)
        return [({"roll": roll}, (0.4, -0.4), 0.35), ({"roll": roll * 1.05, "pitch": DEG(-4)}, (0.4, -0.4), 0.7), ({}, (0.0, 0.0), 0.4)]
    if action in ("giggle", "pat_end"):
        flick = 0.5
        return [({"pitch": DEG(6)}, (flick, flick), 0.14), ({"pitch": DEG(-3)}, (-flick, -flick), 0.14),
                ({"pitch": DEG(6)}, (flick, flick), 0.14), ({"pitch": DEG(-3)}, (-flick, -flick), 0.14), ({}, (0.0, 0.0), 0.2)]
    if action == "hop":
        return [({"z": -0.006}, None, 0.12), ({"z": 0.018, "pitch": DEG(-8)}, (0.8, -0.8), 0.2), ({}, (0.0, 0.0), 0.35)]
    if action in ("pat_start", "pat_demo"):
        return [({"pitch": DEG(12), "roll": DEG(4)}, (-0.6, 0.6), 0.5)]
    if action == "wake":
        return [({"pitch": DEG(-8)}, (0.7, -0.7), 0.25), ({}, (0.0, 0.0), 0.4)]
    if action == "menu_open":
        return [({"pitch": DEG(-6)}, (0.5, -0.5), 0.35), ({}, (0.0, 0.0), 0.5)]
    if action == "menu_next":
        return [({}, (0.3, -0.3), 0.12), ({}, (0.0, 0.0), 0.15)]
    return []


def recorded_move(action: str) -> Optional[str]:
    """Bigger feelings reuse the photo emotion table, so both bodies agree."""
    from bridge import scene_agent

    def pick(emotion: str, tier: int) -> str:
        return random.choice(scene_agent.EMOTION_MAP[emotion]["moves"][tier])

    if action in ("laugh", "photo_demo"):
        return pick("joy", 0)
    if action == "question":  # the side button's "?" is curiosity
        return pick("curiosity", 1)
    if action == "replay":
        return scene_agent._last_move or pick("joy", 1)
    return {"snack": "grateful1", "dance": "dance1", "miss": "loving1", "sleep": "sleep1"}.get(action)


class ReachyMirror:
    """Plays M5 actions on Reachy one at a time; the newest waiting action wins."""

    PAT_LIMIT_S = 20.0

    def __init__(self) -> None:
        self.pending: Dict[str, Any] | None = None
        self.ready = threading.Condition()
        self.patting = False
        self.played = 0
        self.last: Dict[str, Any] = {}
        threading.Thread(target=self._work, daemon=True).start()

    def handle(self, message: Dict[str, Any]) -> None:
        """M5Link listener: take m5_action events, ignore everything else."""
        if message.get("type") != "m5_action":
            return
        action = message.get("action", "")
        with self.ready:
            if action == "pat_start":
                self.patting = True
            elif action in ("pat_end", "wake", "menu_close"):
                self.patting = False
            if action == "menu_close":
                return
            if self.pending is not None:
                logger.info("replacing waiting %s with %s", self.pending.get("action"), action)
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
        action = str(message.get("action", ""))
        started = time.time()
        if not self._wait_idle(2.0):
            logger.info("another move is playing; skipped %s", action)
            return {"skipped": True}
        frames = gesture_frames(action, float(message.get("strength", 0.7)))
        move = None if frames else recorded_move(action)
        if frames:
            sent = self._run(frames)
            if action == "pat_start":
                sent += self._hold_pat(frames[-1])
        elif move:
            from bridge.scene_agent import play

            play(move, with_sound=WITH_SOUND)
            sent = 1
        else:
            return {}
        self.played += 1
        self.last = {"action": action, "move": move, "moves": sent, "seconds": round(time.time() - started, 2),
                     "axis": message.get("axis"), "src": message.get("src"), "injected": bool(message.get("injected"))}
        logger.info("mirrored on Reachy: %s", self.last)
        return self.last

    def _run(self, frames: List[Frame]) -> int:
        head = _call("GET", "/api/state/present_head_pose?use_pose_matrix=false")
        try:
            antennas = _call("GET", "/api/state/present_antenna_joint_positions")
            base_antennas = (float(antennas[0]), float(antennas[1]))
        except Exception:
            base_antennas = (0.0, 0.0)
        sent = 0
        for offset, antenna_offset, seconds in frames:
            pose = {key: head.get(key, 0.0) + offset.get(key, 0.0) for key in ("x", "y", "z", "roll", "pitch", "yaw")}
            body: Dict[str, Any] = {"head_pose": pose, "duration": seconds}
            if antenna_offset is not None:
                body["antennas"] = [base_antennas[0] + antenna_offset[0], base_antennas[1] + antenna_offset[1]]
            _call("POST", "/api/move/goto", body)
            sent += 1
            time.sleep(seconds)
            self._wait_idle(0.5)
        return sent

    def _hold_pat(self, frame: Frame) -> int:
        """Keep the head bowed under the hand until it lets go, then giggle."""
        sent, deadline = 0, time.monotonic() + self.PAT_LIMIT_S
        while self.patting and time.monotonic() < deadline:
            with self.ready:
                if self.pending is not None and self.pending.get("action") != "pat_end":
                    break
            sent += self._run([(frame[0], frame[1], 0.8)])
        return sent

    @staticmethod
    def _wait_idle(timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not _call("GET", "/api/move/running"):
                return True
            time.sleep(0.02)
        return False


def configure(link: Any) -> None:
    """Send any axis calibration from the environment to the M5 (RAM only on the stick)."""
    config = {k: v for k, v in (("gyro", os.getenv("M5_GYRO_MAP")), ("accel", os.getenv("M5_ACCEL_MAP"))) if v}
    if config:
        link.send({"type": "imu_config", **config})


def main() -> int:
    """Mirror the M5 on Reachy without the glasses: `python -m bridge.m5_motion`."""
    import sys
    from bridge.m5_link import M5Link

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    link = M5Link(os.getenv("M5_PORT") or None)
    mirror = ReachyMirror()
    link.listeners.append(mirror.handle)
    link.listeners.append(lambda m: m.get("type") == "m5_action" and logger.info("M5 says: %s", m))
    if not link.connect():
        print("M5 not found", file=sys.stderr)
        return 1
    configure(link)
    print("Mirroring the M5 on Reachy. Ctrl+C to stop.", flush=True)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

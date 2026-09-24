"""Watch the robot's camera for hand gestures, and notice a wave.

A wave is not a pose, it is a pose that moves: an open palm whose wrist crosses
back and forth. MediaPipe's gesture recognizer gives both the static label and
the 21 landmarks per frame, so the wave falls out of the wrist's horizontal
track - no training set needed. Static gestures (open palm, fist, thumb up,
victory, pointing) come free from the same model.

The watcher runs in a background thread and pulls frames from the same
MediaManager the conversation app already owns, so it never contends with the
app for the camera.
"""

import time
import queue
import logging
import threading
from typing import Any, Dict, List, Tuple
from pathlib import Path
from collections import deque

import numpy as np

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

MODEL_PATH = Path(r"D:\海风\models\gesture_recognizer.task")
DAEMON = "http://127.0.0.1:8000"
EMOTIONS_DATASET = "pollen-robotics/reachy-mini-emotions-library"

SAMPLE_HZ = 10.0
WINDOW_S = 2.0
# A wave needs the wrist to actually travel, not just jitter: normalised image
# width, so 0.10 is a tenth of the frame.
MIN_TRAVEL = 0.10
MIN_REVERSALS = 3
# Ignore reversals smaller than this, otherwise landmark noise counts as waving.
MIN_SEGMENT = 0.02
OPEN_PALM_RATIO = 0.5
REFIRE_COOLDOWN_S = 6.0
REACTION_MOVE = "welcoming1"

# Head following. The head leans towards the hand rather than chasing it to the
# edge of frame: 0.0 stares straight ahead, 1.0 puts the hand dead centre.
FOLLOW_GAIN = 0.6
# Exponential smoothing on the tracked point, so landmark jitter is not a twitch.
FOLLOW_SMOOTHING = 0.45
# Ignore sub-pixel-ish moves; below this the head holds still.
FOLLOW_DEADZONE = 0.015


class _Watcher(threading.Thread):
    """Sample the camera and raise an event when the wrist track looks like a wave."""

    def __init__(self, deps: ToolDependencies) -> None:
        """Prepare the thread; the model loads once `run` starts."""
        super().__init__(name="gesture-watch", daemon=True)
        self.deps = deps
        self._stop = threading.Event()
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=32)
        self.frames_seen = 0
        self.hands_seen = 0
        self.waves = 0
        self.last_gesture: str | None = None
        self.last_wave_at: float | None = None
        self.error: str | None = None
        self.react = True
        self.follow = True
        self.follow_errors = 0
        self._smoothed: Tuple[float, float] | None = None
        self._track: deque[Tuple[float, float, str]] = deque(maxlen=int(SAMPLE_HZ * WINDOW_S) + 4)

    # ---- detection ----------------------------------------------------------

    @staticmethod
    def _reversals(values: List[float]) -> Tuple[int, float]:
        """Count meaningful direction changes and total travel along one axis."""
        if len(values) < 3:
            return 0, 0.0
        travel = 0.0
        reversals = 0
        direction = 0
        anchor = values[0]
        for previous, current in zip(values, values[1:]):
            travel += abs(current - previous)
            delta = current - anchor
            if abs(delta) < MIN_SEGMENT:
                continue
            step = 1 if delta > 0 else -1
            if direction != 0 and step != direction:
                reversals += 1
            direction = step
            anchor = current
        return reversals, travel

    def _looks_like_wave(self) -> bool:
        now = time.time()
        recent = [entry for entry in self._track if now - entry[0] <= WINDOW_S]
        if len(recent) < int(SAMPLE_HZ * 0.8):
            return False
        open_palm = sum(1 for _, _, label in recent if label in ("Open_Palm", "Victory"))
        if open_palm < len(recent) * OPEN_PALM_RATIO:
            return False
        reversals, travel = self._reversals([x for _, x, _ in recent])
        return reversals >= MIN_REVERSALS and travel >= MIN_TRAVEL

    # ---- reaction -----------------------------------------------------------

    def _wave_back(self) -> None:
        """Greet back on the robot itself, so a wave gets an answer immediately."""
        self._post(f"/api/move/play/recorded-move-dataset/{EMOTIONS_DATASET}/{REACTION_MOVE}")

    @staticmethod
    def _post(path: str) -> None:
        import urllib.request

        try:
            request = urllib.request.Request(DAEMON + path, data=b"", method="POST")
            with urllib.request.urlopen(request, timeout=8):
                pass
        except Exception as error:
            logger.warning("POST %s failed: %s", path, error)

    def _follow_hand(self, x: float, y: float, width: int, height: int) -> None:
        """Lean the head towards the hand, partway rather than all the way."""
        previous = self._smoothed
        if previous is None:
            self._smoothed = (x, y)
        else:
            self._smoothed = (
                previous[0] + FOLLOW_SMOOTHING * (x - previous[0]),
                previous[1] + FOLLOW_SMOOTHING * (y - previous[1]),
            )
            if (
                abs(self._smoothed[0] - previous[0]) < FOLLOW_DEADZONE
                and abs(self._smoothed[1] - previous[1]) < FOLLOW_DEADZONE
            ):
                return

        smooth_x, smooth_y = self._smoothed
        # Pull the target back towards the image centre by (1 - gain).
        u = int(width * (0.5 + FOLLOW_GAIN * (smooth_x - 0.5)))
        v = int(height * (0.5 + FOLLOW_GAIN * (smooth_y - 0.5)))
        u = min(max(u, 1), width - 2)
        v = min(max(v, 1), height - 2)
        try:
            # duration 0 streams a target instead of queueing a move, so this
            # never fights the emotion player for the move lock.
            self.deps.reachy_mini.look_at_image(u, v, duration=0.0)
        except Exception as error:
            self.follow_errors += 1
            if self.follow_errors <= 3:
                logger.warning("head follow failed: %s", error)

    # ---- loop ---------------------------------------------------------------

    def run(self) -> None:
        """Sample frames until stopped."""
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            if not MODEL_PATH.exists():
                raise FileNotFoundError(f"gesture model missing at {MODEL_PATH}")

            recognizer = vision.GestureRecognizer.create_from_options(
                vision.GestureRecognizerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
                    running_mode=vision.RunningMode.VIDEO,
                    num_hands=1,
                )
            )
            logger.info("gesture_watch: recognizer ready")
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            logger.exception("gesture_watch failed to start")
            return

        period = 1.0 / SAMPLE_HZ
        started = time.time()
        with recognizer:
            while not self._stop.is_set():
                cycle = time.time()
                try:
                    frame = self.deps.reachy_mini.media.get_frame()
                except Exception as error:
                    self.error = f"frame grab failed: {error}"
                    time.sleep(1.0)
                    continue
                if frame is None:
                    time.sleep(period)
                    continue

                self.frames_seen += 1
                bgr = np.asarray(frame)
                rgb = np.ascontiguousarray(bgr[:, :, ::-1])
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp_ms = int((time.time() - started) * 1000)
                try:
                    result = recognizer.recognize_for_video(image, timestamp_ms)
                except Exception as error:
                    logger.debug("recognize failed: %s", error)
                    time.sleep(period)
                    continue

                if result.hand_landmarks:
                    self.hands_seen += 1
                    wrist = result.hand_landmarks[0][0]
                    label = "None"
                    if result.gestures and result.gestures[0]:
                        label = result.gestures[0][0].category_name
                    self.last_gesture = label
                    self._track.append((time.time(), float(wrist.x), label))

                    if self.follow:
                        height, width = bgr.shape[:2]
                        self._follow_hand(float(wrist.x), float(wrist.y), width, height)

                    now = time.time()
                    cooled = self.last_wave_at is None or now - self.last_wave_at > REFIRE_COOLDOWN_S
                    if cooled and self._looks_like_wave():
                        self.waves += 1
                        self.last_wave_at = now
                        self._track.clear()
                        logger.info("gesture_watch: wave detected (#%d)", self.waves)
                        try:
                            self.events.put_nowait({"gesture": "wave", "at": now})
                        except queue.Full:
                            pass
                        if self.react:
                            self._wave_back()
                else:
                    self.last_gesture = None
                    # Forget the track so the head does not snap when a hand
                    # reappears somewhere else.
                    self._smoothed = None

                elapsed = time.time() - cycle
                if elapsed < period:
                    time.sleep(period - elapsed)

    def stop(self) -> None:
        """Ask the thread to finish after the current frame."""
        self._stop.set()


_watcher: _Watcher | None = None
_watcher_lock = threading.Lock()


def _ensure_watcher(deps: ToolDependencies) -> _Watcher:
    global _watcher
    with _watcher_lock:
        if _watcher is None or not _watcher.is_alive():
            _watcher = _Watcher(deps)
            _watcher.start()
        return _watcher


class GestureWatch(Tool):
    """Arm the camera watcher and report what it has seen."""

    name = "gesture_watch"
    description = (
        "Watch the camera for hand gestures in the background, so you notice when someone "
        "waves at you without being told. Use action='enable' when the user mentions waving, "
        "gestures, hand signals, or asks you to watch them - and at the start of a conversation "
        "if they have asked for gesture interaction before. "
        "Use action='status' to check whether anyone has waved since you last looked, and what "
        "hand gesture is visible right now (open palm, fist, thumb up, victory, pointing). "
        "Use action='disable' to stop watching. "
        "When status reports a wave, greet them back warmly - the robot has already waved."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["enable", "disable", "status"],
                "description": "Arm the watcher, stop it, or read what it has seen.",
            },
            "react": {
                "type": "boolean",
                "description": "Whether the robot should wave back by itself. Default true.",
            },
            "follow": {
                "type": "boolean",
                "description": (
                    "Whether the head should lean towards the hand as it moves. Default true. "
                    "This takes over the head, so face tracking is turned off while it runs."
                ),
            },
        },
        "required": ["action"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        """Run one gesture-watch action."""
        global _watcher
        action = (kwargs.get("action") or "").strip().lower()

        if action == "disable":
            with _watcher_lock:
                if _watcher is not None:
                    _watcher.stop()
                    _watcher = None
            return {"watching": False}

        if action == "enable":
            if not deps.camera_enabled:
                return {"error": "Camera is disabled"}
            watcher = _ensure_watcher(deps)
            if kwargs.get("react") is not None:
                watcher.react = bool(kwargs["react"])
            if kwargs.get("follow") is not None:
                watcher.follow = bool(kwargs["follow"])
            if watcher.follow:
                # Face tracking drives the head from the daemon side; leaving it on
                # would make the two fight for the same joints every frame.
                watcher._post("/api/media/tracking/disable")
            time.sleep(0.2)
            return {
                "watching": watcher.is_alive(),
                "error": watcher.error,
                "reacts_by_itself": watcher.react,
                "head_follows_hand": watcher.follow,
            }

        if action != "status":
            return {"error": "action must be one of enable, disable, status"}

        watcher = _watcher
        if watcher is None or not watcher.is_alive():
            return {"watching": False, "hint": "call action='enable' first"}

        waves: List[Dict[str, Any]] = []
        while True:
            try:
                waves.append(watcher.events.get_nowait())
            except queue.Empty:
                break

        return {
            "watching": True,
            "new_waves": len(waves),
            "waved_just_now": bool(waves),
            "current_gesture": watcher.last_gesture,
            "frames_sampled": watcher.frames_seen,
            "frames_with_a_hand": watcher.hands_seen,
            "waves_total": watcher.waves,
            "head_follows_hand": watcher.follow,
            "error": watcher.error,
        }

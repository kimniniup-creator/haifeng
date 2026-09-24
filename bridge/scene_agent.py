"""Turn a photo into one Reachy reaction.

The vision model is asked for a structured reading of the scene rather than
prose, so the mapping from feeling to movement stays here in code: the model
never names a move, and swapping the emotion library does not mean reprompting.

The relay this talks to sits behind Cloudflare, which answers a default urllib
User-Agent with error 1010. The OpenAI SDK sends its own, so use the SDK.
"""

import os
import json
import random
import base64
import logging
from typing import Any, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

DAEMON = os.getenv("REACHY_DAEMON_URL", "http://127.0.0.1:8000")
EMOTIONS_DATASET = "pollen-robotics/reachy-mini-emotions-library"

# Longest edge the photo is scaled to before upload. The glasses already send a
# small AI frame; this only guards against a full-resolution one.
MAX_EDGE = 768
JPEG_QUALITY = 78

# A frame too dark or too smeared to hold a scene. The model cannot be relied on
# to disown one: shown a black, motion-blurred capture it answered confidence
# 0.97 - confident that the view *was* "very dark and heavily motion-blurred",
# which is an honest reading of the pixels and a useless basis for a reaction.
# So judge the frame here, where it is measurable, and cap the confidence.
# Measured on this hardware: readable frames ran mean 44-72 with Laplacian
# variance 60-230; the unreadable one was mean 22 with variance 12.
MIN_BRIGHTNESS = 30.0
MIN_SHARPNESS = 25.0
UNREADABLE_CONFIDENCE = 0.0

EMOTIONS = (
    "joy", "affection", "surprise", "curiosity",
    "sadness", "fear", "anger", "neutral",
)

# One table for both bodies: per feeling, Reachy's moves at strong / medium /
# soft intensity (several each, so the same photo mood does not always look
# identical), and how the M5 pocket window acts it out. All names verified
# against the live library (85 moves). Negative feelings get empathy on Reachy,
# never contempt; the M5 still ends in a gentle laugh.
EMOTION_MAP: Dict[str, Dict[str, Any]] = {
    "joy": {"m5": "delighted", "moves": (
        ("laughing1", "laughing2", "success1"),
        ("cheerful1", "enthusiastic1", "proud1"),
        ("enthusiastic2", "welcoming1"))},
    "affection": {"m5": "love", "moves": (
        ("loving1",),
        ("grateful1", "welcoming2"),
        ("serenity1", "shy1"))},
    "surprise": {"m5": "wow", "moves": (
        ("amazed1", "electric1"),
        ("surprised1", "oops1"),
        ("surprised2", "oops2"))},
    "curiosity": {"m5": "curious", "moves": (
        ("curious1", "inquiring3"),
        ("inquiring1", "thoughtful1"),
        ("inquiring2", "thoughtful2"))},
    "sadness": {"m5": "gentle", "moves": (
        ("sad1", "lonely1"),
        ("sad2", "downcast1"),
        ("yes_sad1", "resigned1"))},
    "fear": {"m5": "gentle", "moves": (
        ("scared1", "fear1"),
        ("anxiety1", "uncomfortable1"),
        ("uncertain1",))},
    "anger": {"m5": "gentle", "moves": (
        ("irritated2", "frustrated1"),
        ("irritated1", "displeased1"),
        ("displeased2", "uncomfortable1"))},
    "neutral": {"m5": "neutral", "moves": (
        ("attentive1", "understanding1"),
        ("understanding2", "attentive2"),
        ("attentive2", "understanding1"))},
}
EMOTION_MOVES = {name: entry["moves"] for name, entry in EMOTION_MAP.items()}

# Below this the reading is not trusted enough to act it out.
MIN_CONFIDENCE = 0.5
FALLBACK_MOVE = "attentive1"
_last_move = ""

PROMPT = (
    "You are the perception stage for a small desk robot. You get one photo taken "
    "from the wearer's glasses. Read the moment, not the pixels.\n\n"
    "Reply with JSON only, no prose, no code fence:\n"
    '{"scene": "<one short sentence>", '
    f'"emotion": "<one of: {", ".join(EMOTIONS)}>", '
    '"intensity": <0.0-1.0>, "confidence": <0.0-1.0>, '
    '"utterance": "<one short warm sentence the robot could say, or empty>", '
    '"line_zh": "<the same feeling as one short spoken Chinese line for a tiny '
    'pocket screen, at most 14 characters, no emoji, no line breaks>"}\n\n'
    "emotion is what the ROBOT should express in response, not what it sees. "
    "Set confidence low when the photo is dark, blurred, or ambiguous - a wrong "
    "confident answer is worse than an unsure one."
)


def _client() -> Any:
    from openai import OpenAI

    key = os.getenv("SCENE_API_KEY")
    url = os.getenv("SCENE_API_URL")
    if not key or not url:
        raise RuntimeError("SCENE_API_KEY and SCENE_API_URL must be set (see .env)")
    return OpenAI(api_key=key, base_url=url.rstrip("/") + "/v1")


def shrink(image: bytes) -> bytes:
    """Scale the photo down so uploads stay small; pass it through if cv2 is absent."""
    try:
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return image
        height, width = frame.shape[:2]
        longest = max(height, width)
        if longest > MAX_EDGE:
            scale = MAX_EDGE / longest
            frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        return buffer.tobytes() if ok else image
    except Exception:
        return image


def readable(image: bytes) -> tuple[bool, str]:
    """Whether the frame carries enough light and detail to be worth reading.

    Returns (ok, reason). Without cv2 nothing can be measured, so say yes and
    let the model decide rather than silently muting every reaction.
    """
    try:
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return False, "frame did not decode"
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(grey.mean())
        sharpness = float(cv2.Laplacian(grey, cv2.CV_64F).var())
        if brightness < MIN_BRIGHTNESS:
            return False, f"too dark (mean {brightness:.0f} < {MIN_BRIGHTNESS:.0f})"
        if sharpness < MIN_SHARPNESS:
            return False, f"too blurred (variance {sharpness:.0f} < {MIN_SHARPNESS:.0f})"
        return True, f"mean {brightness:.0f}, variance {sharpness:.0f}"
    except Exception as error:
        logger.debug("frame quality not measurable: %s", error)
        return True, "not measured"


def analyse(image: bytes, model: str | None = None, timeout: float = 90.0) -> Dict[str, Any]:
    """Ask the vision model how the robot should react to this photo."""
    payload = shrink(image)
    encoded = base64.b64encode(payload).decode()
    model = model or os.getenv("SCENE_MODEL", "gpt-5.6-sol")

    response = _client().with_options(timeout=timeout).chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                    },
                ],
            }
        ],
        max_tokens=300,
    )
    text = (response.choices[0].message.content or "").strip()
    reading = _parse(text)

    # Cap rather than replace: the model's own words are still worth keeping in
    # the log, and every other key stays exactly as the caller expects it.
    ok, reason = readable(payload)
    if not ok and reading["confidence"] > UNREADABLE_CONFIDENCE:
        logger.info("unreadable frame (%s); confidence %.2f -> %.2f",
                    reason, reading["confidence"], UNREADABLE_CONFIDENCE)
        reading["confidence"] = UNREADABLE_CONFIDENCE
        reading["quality"] = reason
    return reading


def _parse(text: str) -> Dict[str, Any]:
    """Pull the JSON object out of the reply and clamp it into range."""
    body = text
    if body.startswith("```"):
        body = body.split("```")[1]
        body = body.split("\n", 1)[1] if "\n" in body else body
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"model did not return JSON: {text[:200]}")
    data = json.loads(body[start : end + 1])

    emotion = str(data.get("emotion", "")).strip().lower()
    if emotion not in EMOTION_MOVES:
        logger.warning("unknown emotion %r from model; treating as neutral", emotion)
        emotion = "neutral"

    def ratio(key: str, default: float) -> float:
        try:
            return min(max(float(data.get(key, default)), 0.0), 1.0)
        except (TypeError, ValueError):
            return default

    return {
        "scene": str(data.get("scene", "")).strip(),
        "emotion": emotion,
        "intensity": ratio("intensity", 0.5),
        "confidence": ratio("confidence", 0.5),
        "utterance": str(data.get("utterance", "")).strip(),
        "line_zh": str(data.get("line_zh", "")).strip(),
    }


def choose_move(analysis: Dict[str, Any]) -> str:
    """Pick the move for a reading, or hold back when the model is unsure."""
    global _last_move
    if analysis["confidence"] < MIN_CONFIDENCE:
        return FALLBACK_MOVE
    strong, medium, soft = EMOTION_MOVES[analysis["emotion"]]
    intensity = analysis["intensity"]
    tier = strong if intensity >= 0.7 else medium if intensity >= 0.4 else soft
    choices = [move for move in tier if move != _last_move] or list(tier)
    _last_move = random.choice(choices)
    return _last_move


def m5_expression(analysis: Dict[str, Any]) -> str:
    """How the pocket window acts out the same reading; unsure means neutral."""
    if analysis["confidence"] < MIN_CONFIDENCE:
        return "neutral"
    return EMOTION_MAP[analysis["emotion"]]["m5"]


def play(move: str, with_sound: bool = True, timeout: float = 15.0) -> Dict[str, Any]:
    """Play one recorded move on the robot, with its bundled audio when asked."""
    import urllib.request

    result: Dict[str, Any] = {"move": move, "motion": None, "sound": None}

    if with_sound:
        sound = _sound_path(move)
        # The daemon answers 200 {"status":"ok"} even for a path that does not
        # exist, so the status alone never shows whether anything was audible.
        # Record the file that was actually sent; a silent move is then one
        # lookup away from an answer instead of a guess.
        result["sound_file"] = str(sound) if sound is not None else None
        if sound is not None:
            result["sound"] = _post(
                "/api/media/play_sound", {"file": str(sound)}, timeout=timeout
            )

    result["motion"] = _post(
        f"/api/move/play/recorded-move-dataset/{EMOTIONS_DATASET}/{move}", None, timeout=timeout
    )
    return result


def _post(path: str, body: Dict[str, Any] | None, timeout: float) -> str:
    import urllib.request

    data = json.dumps(body).encode() if body is not None else b""
    request = urllib.request.Request(
        DAEMON + path, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return f"{response.status}"
    except Exception as error:
        logger.warning("POST %s failed: %s", path, error)
        return f"failed: {error}"


def _dataset_roots() -> list[Path]:
    """Every local copy of the emotion dataset, preferring the hub's own answer."""
    roots: list[Path] = []
    try:
        from huggingface_hub import snapshot_download

        roots.append(Path(snapshot_download(EMOTIONS_DATASET, repo_type="dataset")))
    except Exception as error:
        logger.debug("snapshot_download unavailable: %s", error)

    # Fall back to the cache layout directly, so a venv without huggingface_hub
    # still finds the audio instead of silently playing a mute move.
    cache = Path(
        os.getenv("HF_HOME")
        or Path.home() / ".cache" / "huggingface"
    )
    if cache.name != "huggingface" and (cache / "huggingface").is_dir():
        cache = cache / "huggingface"
    snapshots = cache / "hub" / (
        "datasets--" + EMOTIONS_DATASET.replace("/", "--")
    ) / "snapshots"
    if snapshots.is_dir():
        roots.extend(sorted(snapshots.iterdir(), reverse=True))
    return roots


def _sound_path(move: str) -> Path | None:
    """Locate the move's bundled ogg in the local HuggingFace cache."""
    for root in _dataset_roots():
        for candidate in (root / f"{move}.ogg", root / "data" / f"{move}.ogg"):
            if candidate.exists():
                return candidate
    logger.debug("no bundled audio found for %s", move)
    return None


def react(image: bytes, with_sound: bool = True) -> Dict[str, Any]:
    """Analyse one photo and act on it. Returns the reading plus what was played."""
    analysis = analyse(image)
    move = choose_move(analysis)
    analysis["move"] = move
    analysis["m5_expression"] = m5_expression(analysis)
    analysis["played"] = play(move, with_sound=with_sound)
    return analysis

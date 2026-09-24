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

EMOTIONS = (
    "joy", "affection", "surprise", "curiosity",
    "sadness", "fear", "anger", "neutral",
)

# Strong / medium / soft per feeling. Names verified against the live library.
EMOTION_MOVES: Dict[str, tuple[str, str, str]] = {
    "joy": ("laughing1", "cheerful1", "enthusiastic1"),
    "affection": ("loving1", "grateful1", "serenity1"),
    "surprise": ("amazed1", "surprised1", "surprised2"),
    "curiosity": ("curious1", "inquiring1", "inquiring2"),
    "sadness": ("sad1", "sad2", "downcast1"),
    "fear": ("scared1", "anxiety1", "uncertain1"),
    "anger": ("irritated1", "displeased2", "contempt1"),
    "neutral": ("attentive1", "understanding2", "attentive2"),
}

# Below this the reading is not trusted enough to act it out.
MIN_CONFIDENCE = 0.5
FALLBACK_MOVE = "attentive1"

PROMPT = (
    "You are the perception stage for a small desk robot. You get one photo taken "
    "from the wearer's glasses. Read the moment, not the pixels.\n\n"
    "Reply with JSON only, no prose, no code fence:\n"
    '{"scene": "<one short sentence>", '
    f'"emotion": "<one of: {", ".join(EMOTIONS)}>", '
    '"intensity": <0.0-1.0>, "confidence": <0.0-1.0>, '
    '"utterance": "<one short warm sentence the robot could say, or empty>"}\n\n'
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
    return _parse(text)


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
    }


def choose_move(analysis: Dict[str, Any]) -> str:
    """Pick the move for a reading, or hold back when the model is unsure."""
    if analysis["confidence"] < MIN_CONFIDENCE:
        return FALLBACK_MOVE
    strong, medium, soft = EMOTION_MOVES[analysis["emotion"]]
    intensity = analysis["intensity"]
    return strong if intensity >= 0.7 else medium if intensity >= 0.4 else soft


def play(move: str, with_sound: bool = True, timeout: float = 15.0) -> Dict[str, Any]:
    """Play one recorded move on the robot, with its bundled audio when asked."""
    import urllib.request

    result: Dict[str, Any] = {"move": move, "motion": None, "sound": None}

    if with_sound:
        sound = _sound_path(move)
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
    analysis["played"] = play(move, with_sound=with_sound)
    return analysis

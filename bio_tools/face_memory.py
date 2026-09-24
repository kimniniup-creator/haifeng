"""Remember and recognise faces with the robot's own camera.

YuNet detects, SFace embeds; both ship with OpenCV and are cached from the
official OpenCV Zoo mirror on HuggingFace. Embeddings live in a local JSON
next to the robot's other user data and never leave the machine.
"""

import json
import asyncio
import logging
import threading
from typing import Any, Dict, List, Tuple
from pathlib import Path

import numpy as np

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

# SFace's own cosine threshold from the OpenCV Zoo reference implementation.
# Above this two crops are the same person; we keep a margin band below it so a
# near-miss is reported as "not sure" instead of a confident wrong name.
MATCH_THRESHOLD = 0.363
UNSURE_THRESHOLD = 0.28

# Frames averaged per enrolment. The camera is live, so a short burst covers
# small pose and lighting changes without asking the person to hold still.
ENROL_FRAMES = 7
ENROL_INTERVAL_S = 0.25

DB_PATH = Path(r"D:\海风\data\face_db.json")

_lock = threading.Lock()
_models: Tuple[Any, Any] | None = None


def _load_models() -> Tuple[Any, Any]:
    """Load YuNet + SFace once, from the HuggingFace cache."""
    global _models
    with _lock:
        if _models is None:
            import cv2
            from huggingface_hub import hf_hub_download

            detector_path = hf_hub_download(
                "opencv/face_detection_yunet", "face_detection_yunet_2023mar.onnx"
            )
            recogniser_path = hf_hub_download(
                "opencv/face_recognition_sface", "face_recognition_sface_2021dec.onnx"
            )
            detector = cv2.FaceDetectorYN.create(detector_path, "", (320, 320))
            recogniser = cv2.FaceRecognizerSF.create(recogniser_path, "")
            _models = (detector, recogniser)
            logger.info("face_memory: YuNet and SFace loaded")
    return _models


def _read_db() -> Dict[str, List[List[float]]]:
    try:
        raw = json.loads(DB_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    people = raw.get("people")
    return people if isinstance(people, dict) else {}


def _write_db(people: Dict[str, List[List[float]]]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "people": people}
    temporary = DB_PATH.with_name(f".{DB_PATH.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(DB_PATH)


def _largest_face(frame: np.ndarray) -> np.ndarray | None:
    """Return the biggest detected face row, or None when nobody is in shot."""
    detector, _ = _load_models()
    height, width = frame.shape[:2]
    detector.setInputSize((width, height))
    _, faces = detector.detect(frame)
    if faces is None or len(faces) == 0:
        return None
    # Column 2 and 3 are the box width and height.
    return max(faces, key=lambda row: float(row[2]) * float(row[3]))


def _embed(frame: np.ndarray) -> np.ndarray | None:
    """Align the largest face and return its L2-normalised SFace embedding."""
    face = _largest_face(frame)
    if face is None:
        return None
    _, recogniser = _load_models()
    aligned = recogniser.alignCrop(frame, face)
    vector = np.asarray(recogniser.feature(aligned), dtype=np.float32).ravel()
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else None


def _similarity(vector: np.ndarray, stored: List[List[float]]) -> float:
    """Best cosine similarity against any sample enrolled for one person."""
    best = -1.0
    for sample in stored:
        reference = np.asarray(sample, dtype=np.float32)
        norm = float(np.linalg.norm(reference))
        if norm == 0:
            continue
        best = max(best, float(np.dot(vector, reference / norm)))
    return best


def _capture_embeddings(get_frame, count: int) -> List[np.ndarray]:
    """Grab a short burst of frames and keep the ones holding a face."""
    import time

    collected: List[np.ndarray] = []
    for _ in range(count):
        frame = get_frame()
        if frame is not None:
            vector = _embed(np.asarray(frame))
            if vector is not None:
                collected.append(vector)
        time.sleep(ENROL_INTERVAL_S)
    return collected


class FaceMemory(Tool):
    """Enrol and recognise the people the robot has been introduced to."""

    name = "face_memory"
    description = (
        "Remember or recognise a person by their face, using the robot's camera. "
        "Use action='enrol' with a name when someone asks you to remember them, learn their face, "
        "or says something like 'I'm Kim, remember me'. "
        "Use action='identify' when someone asks who you see, whether you recognise them, "
        "or who they are. Use action='list' to say whose faces you already know, and "
        "action='forget' with a name to erase one person. "
        "Faces are stored only on this robot."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["enrol", "identify", "list", "forget"],
                "description": "What to do with the face memory.",
            },
            "name": {
                "type": "string",
                "description": "Person's name. Required for 'enrol' and 'forget'.",
            },
        },
        "required": ["action"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        """Run one face-memory action against the live camera."""
        action = (kwargs.get("action") or "").strip().lower()
        name = (kwargs.get("name") or "").strip()

        if action == "list":
            people = await asyncio.to_thread(_read_db)
            return {"known_people": sorted(people), "count": len(people)}

        if action == "forget":
            if not name:
                return {"error": "name is required to forget someone"}
            people = await asyncio.to_thread(_read_db)
            match = next((k for k in people if k.lower() == name.lower()), None)
            if match is None:
                return {"error": f"I do not have a face stored for {name}"}
            people.pop(match)
            await asyncio.to_thread(_write_db, people)
            return {"forgotten": match, "known_people": sorted(people)}

        if action not in ("enrol", "identify"):
            return {"error": "action must be one of enrol, identify, list, forget"}

        if not deps.camera_enabled:
            return {"error": "Camera is disabled"}

        get_frame = deps.reachy_mini.media.get_frame

        if action == "enrol":
            if not name:
                return {"error": "name is required to enrol a face"}
            vectors = await asyncio.to_thread(_capture_embeddings, get_frame, ENROL_FRAMES)
            if not vectors:
                return {"error": "I could not see a face. Ask them to look at me and try again."}
            people = await asyncio.to_thread(_read_db)
            match = next((k for k in people if k.lower() == name.lower()), name)
            people[match] = [v.tolist() for v in vectors]
            await asyncio.to_thread(_write_db, people)
            logger.info("face_memory: enrolled %s from %d frames", match, len(vectors))
            return {"enrolled": match, "samples": len(vectors), "known_people": sorted(people)}

        # identify
        people = await asyncio.to_thread(_read_db)
        if not people:
            return {"recognised": None, "reason": "I have not been introduced to anyone yet"}
        frame = await asyncio.to_thread(get_frame)
        if frame is None:
            return {"error": "No frame available"}
        vector = await asyncio.to_thread(_embed, np.asarray(frame))
        if vector is None:
            return {"recognised": None, "reason": "I cannot see a face right now"}

        scored = sorted(
            ((person, _similarity(vector, samples)) for person, samples in people.items()),
            key=lambda pair: pair[1],
            reverse=True,
        )
        best_name, best_score = scored[0]
        if best_score >= MATCH_THRESHOLD:
            return {"recognised": best_name, "confidence": round(best_score, 3)}
        if best_score >= UNSURE_THRESHOLD:
            return {
                "recognised": None,
                "closest": best_name,
                "confidence": round(best_score, 3),
                "reason": "looks a bit like them but I am not sure",
            }
        return {
            "recognised": None,
            "confidence": round(best_score, 3),
            "reason": "this is someone I have not met",
        }

"""Explicit model download only; no camera, audio, or cloud inference."""
from pathlib import Path
from urllib.request import urlopen
import hashlib

URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / ".runtime/models/hand_landmarker.task"
    target.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(URL, timeout=30) as response:
        data = response.read(20_000_000)
    if len(data) >= 20_000_000:
        raise RuntimeError("Unexpected model size")
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("Model hash mismatch; nothing written")
    target.write_bytes(data)
    print(f"Model downloaded: {len(data)} bytes, SHA256 {hashlib.sha256(data).hexdigest()}")

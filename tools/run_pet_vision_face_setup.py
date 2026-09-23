"""Explicit official Face Landmarker model download, no media/device access."""
from pathlib import Path
from urllib.request import urlopen
import hashlib

URL='https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
SHA256='64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'


if __name__=='__main__':
    target=Path(__file__).resolve().parents[1]/'.runtime/models/face_landmarker.task'
    with urlopen(URL,timeout=30) as response:
        data=response.read(20_000_000)
    if len(data)>=20_000_000:
        raise RuntimeError('Unexpected model size')
    if hashlib.sha256(data).hexdigest()!=SHA256:
        raise RuntimeError('Unexpected model hash; nothing written')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(data)
    print({'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})

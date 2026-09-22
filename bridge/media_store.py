from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import io
import os
import uuid

from PIL import Image


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 12_000_000
ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png"}


@dataclass(frozen=True)
class StoredImage:
    image_id: str
    path: Path
    mime_type: str
    sha256: str
    width: int
    height: int
    byte_size: int
    source: str
    captured_at: str


class MediaStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, source: str, captured_at: str | None = None) -> StoredImage:
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("IMAGE_TOO_LARGE")
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image_format = image.format or ""
                width, height = image.size
        except Exception as exc:
            raise ValueError("IMAGE_INVALID") from exc
        if image_format not in ALLOWED_FORMATS:
            raise ValueError("IMAGE_FORMAT_UNSUPPORTED")
        if width * height > MAX_PIXELS:
            raise ValueError("IMAGE_PIXELS_TOO_LARGE")

        image_id = f"img_{uuid.uuid4().hex}"
        digest = hashlib.sha256(content).hexdigest()
        suffix = ".jpg" if image_format == "JPEG" else ".png"
        target = self.root / f"{image_id}{suffix}"
        temporary = self.root / f".{image_id}.tmp"
        temporary.write_bytes(content)
        os.replace(temporary, target)
        return StoredImage(
            image_id=image_id,
            path=target,
            mime_type=ALLOWED_FORMATS[image_format],
            sha256=digest,
            width=width,
            height=height,
            byte_size=len(content),
            source=source,
            captured_at=captured_at or datetime.now(timezone.utc).isoformat(),
        )


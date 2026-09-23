"""Lazy optional MediaPipe dependency; no camera or network initialization."""
from typing import Protocol
from .core import Hand, Observation


class Detector(Protocol):
    def detect(self, bgr_frame, observed_at: float) -> Observation: ...
    def close(self): ...


class MediaPipeDetector:
    def __init__(self, model_path, confidence=.7):
        import mediapipe as mp
        self.mp, self.confidence = mp, confidence
        # IMAGE mode accepts arbitrary acquisition times. Temporal logic is ours.
        self.landmarker = mp.tasks.vision.HandLandmarker.create_from_options(
            mp.tasks.vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
                running_mode=mp.tasks.vision.RunningMode.IMAGE, num_hands=2,
                min_hand_detection_confidence=confidence,
                min_hand_presence_confidence=confidence))

    def detect(self, bgr_frame, observed_at):
        import numpy as np
        if bgr_frame.dtype != np.uint8 or bgr_frame.ndim != 3 or bgr_frame.shape[2] != 3:
            raise ValueError("Expected HxWx3 uint8 BGR frame")
        rgb = np.ascontiguousarray(bgr_frame[:, :, ::-1])
        result = self.landmarker.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb))
        # HandLandmarker exposes handedness scores, NOT detection confidence.
        # Never mislabel those; emit the configured acceptance floor explicitly.
        hands = tuple(Hand(tuple((p.x, p.y, p.z) for p in points), self.confidence,
                           result.handedness[i][0].category_name)
                      for i, points in enumerate(result.hand_landmarks))
        return Observation(observed_at, hands)

    def close(self):
        self.landmarker.close()

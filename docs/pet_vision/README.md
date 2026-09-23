# Local pet vision

This package produces backend v1 `presence`, `wave`, and `palm_stop` events. It owns no robot action, TTS, audio, dialogue epoch, daemon, or identity database. `presence` means a visible **hand**, not whole-body presence, face identity, or emotion. An obscured hand is not evidence that a person left the room.

## Install and run

Use an isolated Python 3.12 environment; do not install into the native Reachy or speech environment. Commands run from this repository root:

```powershell
uv venv .runtime/vision-venv --python 3.12
uv pip install --python .runtime/vision-venv/Scripts/python.exe -r requirements-vision.txt pytest==9.1.1
& .runtime/vision-venv/Scripts/python.exe tools/run_pet_vision_setup.py
& .runtime/vision-venv/Scripts/python.exe -m pytest tests/test_pet_vision.py -q
& .runtime/vision-venv/Scripts/python.exe tools/run_pet_vision.py --demo
```

The explicit setup downloads Google's version-1 hand model into ignored `.runtime/models`, checks its SHA256, and performs no inference upload. The demo generates landmarks, not camera pixels. It is a logic demonstration, not evidence of live recognition. The real-model test runs a blank image when the model/dependency is installed and otherwise skips.

For the unified backend, set `PET_API_TOKEN` through the process environment and add `--send`. Metadata goes only to `http://127.0.0.1:8091/v1/events`; redirects and proxies are disabled. Default output is event JSON on stdout. HTTP acceptance is not action completion. Delivery failure stops the runner; there is no stale retry queue.

## Owner integration

`Pipeline(detector, engine, sink).process(Frame(bgr, observed_at))` accepts an owner's HxWx3 uint8 BGR frame. `observed_at` is UTC Unix seconds at acquisition, never inference completion or delivery. `Detector` is a protocol; `MediaPipeDetector` is the real implementation. Tests use generated landmarks and injected detectors. Frames are held only in memory; events contain no pixels, landmarks, biometric template or person ID.

```python
from pet_vision import GestureEngine
from pet_vision.detector import MediaPipeDetector
from pet_vision.pipeline import Pipeline, Frame
detector = MediaPipeDetector('.runtime/models/hand_landmarker.task')
pipeline = Pipeline(detector, GestureEngine(), controller.handle)
# In the existing camera owner's frame callback:
# pipeline.process(Frame(bgr_array, acquisition_utc_seconds))
# On shutdown: detector.close()
```

The MediaPipe output does not expose a calibrated detection confidence. Handedness score is not detection confidence. Positive events therefore carry the configured detection/presence acceptance floor (0.7) with `payload.confidence_basis='configured_detection_floor'`. Synthetic tests provide their own scores. Absence carries `confidence_basis='no_hand_detected'`; its confidence of 1 means the no-detection observation is established, not certainty about a person's absence. Backend owner has aligned vision thresholds to 0.7.

Event fields: `schema_version=1`, `source='vision'`, fresh process `session_id`, unique `event_id`, `kind`, original `observed_at`, `ttl_seconds=1.5`, `confidence`, and `payload`. Presence adds `{present: bool, basis: 'hand'}`; gestures add `stable_ms`. Backend remains responsible for independent TTL, replay, cooldown and priority validation.

## Camera ownership

The audited native SDK 1.8.0 exposes a `win32ipcvideosrc` shared reader. Its REST camera route exposes specs only. Do not construct `ReachyMini`/`MediaManager` merely to obtain frames: they can also initialize audio or acquire devices.

After the media owner confirms the existing shared stream is available, set `PET_VISION_IPC_PYTHON` to the **verified native SDK Python** and run:

```powershell
& .runtime/vision-venv/Scripts/python.exe tools/run_pet_vision.py --provider pet_vision.ipc:frames
```

The optional native helper uses a local anonymous subprocess pipe to keep MediaPipe separate from native SDK dependencies. It checks media availability, consumes only fresh increasing PTS, derives acquisition time from sample running-time and pipeline clock, and stops after 15 seconds. The native reader hard deadline and parent deadline bound hangs. It uses the SDK's private appsink interface verified on native 1.8.0; revalidate on SDK upgrade. Never start a second daemon or call media release/acquire.

If official media is released and the media owner explicitly grants an exclusive raw **video-only** lease, the diagnostic alternative is `--provider pet_vision.ipc:leased_video_frames`. This uses `mfvideosrc` for the verified Reachy video device at 1920x1080 YUY2, 5 fps, downscales in memory to 640x360 BGR, and never opens audio. It refuses if official media is active, stops if it becomes active or daemon errors appear, and does not auto-reconnect. This is an explicit coordinated alternative, not automatic fallback. No guarantee against an external owner racing the lease; coordinate before invoking.

An explicitly verified Windows camera name may be passed through `PET_VISION_DEVICE_NAME` (native helper: `--device-name`). This bypasses device enumeration but does not bypass GStreamer initialization. On this machine Windows PnP lists `Reachy Mini Camera`; even explicit naming did not get through native GStreamer initialization before the hard deadline. No raw camera frame or live gesture success is claimed.

## Recognition boundaries

At least 350 ms stable observations establish presence; 600 ms fresh no-hand observations clear it. No incoming frames mean unknown/stalled input, not inferred absence. Frames older than 750 ms, future by more than 50 ms, duplicate or reordered timestamps are rejected. Inference completion age is checked again.

Open-palm geometry requires extended fingers and separated thumb. A held, spatially stable palm produces one stop per hold. A wave needs at least six open-hand samples, horizontal excursion of 0.12 image widths and multiple direction reversals; vertical travel and jitter are constrained. Both gestures have a two-second global cooldown. Spatial association ignores left/right classification, preventing label flicker from resetting the gesture; tracks reset on disappearance or large gaps. Crossing/occlusion can still lose tracks; there is no persistent identity. A two-hand simultaneous stop is emitted before a wave, with final arbitration delegated to the backend.

These are heuristic gestures. Lighting, hand size, pose, perspective, occlusion and camera frame rate affect results. Palm-stop is a convenience input, **not a hardware emergency stop**. No arm/face-only presence detector is included. Real human wave/palm-stop and final robot feedback remain separate acceptance steps.

## Evidence and upstream sources

Validated locally on Windows/Python 3.12.13 with MediaPipe 1.0.1, NumPy 2.5.3 and OpenCV contrib 5.0.0.93:

- 17 focused tests passed, including TTL/reorder/future rejection, hand-label flips, crossing hands, jitter/cooldown, leave reset, 5 fps palm, and local authenticated HTTP delivery.
- Real model inference: blank image produced no hands; Google's official example image produced two hands with 21 points each, fetched and decoded in memory without saving the image.
- Model SHA256: `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`.
- Live shared source was unavailable (`released=true`, `available=false`). Direct video diagnostic did not return frame statistics; live acquisition and audio/video coexistence remain unverified. Daemon remained running, `error=null`, backend error null and `nb_error=0` after the diagnostic; this does not prove audio quality.

Official [MediaPipe Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python), [model description/card links](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker), [Google sample notebook](https://github.com/google-ai-edge/mediapipe-samples/blob/main/examples/hand_landmarker/python/hand_landmarker.ipynb), and [Reachy media API](https://huggingface.co/docs/reachy_mini/v1.4.1/API/media). MediaPipe/sample code is Apache-2.0; consult the linked upstream model card and package licenses for model/dependency distribution terms. The example notebook attributes its sample image to Unsplash. Neither downloaded model nor sample image is redistributed in this repository.

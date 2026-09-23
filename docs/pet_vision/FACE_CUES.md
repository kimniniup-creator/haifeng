# Observable face cues: stages 1 and 2

Implemented: real local Face Landmarker, face visibility/quality, and sustained `smile` cue. These are observable facial configurations, not inferred inner emotions or identity recognition. No camera was opened during this implementation: the previous producer startup was denied by automatic policy, and this work does not bypass that boundary. Device deployment must use the existing approved single-camera path through its lawful owner.

## Model and quality

MediaPipe 1.0.1 already installed for hands also provides Face Landmarker. Download the official version-1 model explicitly:

```powershell
python tools/run_pet_vision_face_setup.py
python -m pytest tests/test_pet_vision.py tests/test_pet_vision_face.py -q
```

The ignored model is 3,758,596 bytes, SHA256 `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`. Python reads the model bytes into `BaseOptions.model_asset_buffer`, avoiding the previously observed native Unicode filename problem. No image is uploaded. No extra cloud service or face database is introduced.

`MediaPipeFaceDetector.detect(BGR_uint8_frame, acquisition_unix_seconds)` returns a `FaceObservation`. IMAGE mode detects up to two faces and requests blendshape coefficients plus pose transform. Two detected faces mean ambiguous attribution; two is the configured detection cap, not an exhaustive count of every person in a room.

Face quality requires a face at least 80 pixels across its smaller bounding dimension, grayscale mean between 35 and 225, Laplacian variance at least 25, no landmark bounding edge closer than 1% to the image border, and estimated pose within 35 degrees yaw / 30 degrees pitch. Frame exposure/texture are also checked. These configurable heuristics are uncalibrated for the Reachy camera. They do not establish that the eyes are unoccluded, that a depicted face is a live person, or that the expression was intentional.

## Event contract agreed with backend owner

The existing v1 envelope remains: `schema_version=1`, `source='vision'`, per-process session UUID, unique event UUID, original `observed_at`, `ttl_seconds=1.5`, `confidence=0.7`, and payload. Confidence is explicitly a configured detection/presence acceptance floor, **not an emotion probability**.

- `face_presence`: `present` boolean, `face_count`, `face_count_limit=2`, `track_id`, `attribution`, `quality`, `confidence_basis`, `stable_ms`. Positive visibility stabilizes for 300 ms; absence requires 600 ms of usable frames with no detected face. Status renews every 750 ms. No frames means lease expiry/unknown, never manufactured absence.
- `visual_unknown`: same observation metadata plus `unknown_reason`, e.g. `frame_quality`, `multiple_faces`, `face_quality`, `track_stabilizing`, or `no_face_pending`. It triggers no vocal response.
- `visual_cue` with `cue_name='smile'`: requires exactly one usable face, `attribution='single_face'`, at least four consecutive samples over 800 ms with both `mouthSmileLeft` and `mouthSmileRight >= 0.55`. Payload includes those coefficients and thresholds under `rule_basis.version='face-cues-v1'`, `stable_ms`, `interpretation='visible_facial_cue'`, and `provisional=false`.

A smile is latched once per sustained expression, with a global 12-second cooldown. Both smile coefficients must fall to at most 0.35 for 600 ms to rearm. Threshold flicker does not immediately rearm. Every sample must be newer than the last, not more than 50 ms in the future and no older than 750 ms on processing completion. A gap over 400 ms resets the temporary track and pending cue.

`track_id` is a random, in-memory visibility-track UUID. It is reset on absence, unusable quality, multiple faces, a large center jump or a frame gap. It is not a recognized person, does not survive a process restart, and cannot identify the same person returning later. Bounding coordinates and all landmarks remain transient and are not emitted or persisted.

The backend owns voice arbitration and its independent cooldown/TTL checks. No voice epoch is invented by vision. `face_presence`/`visual_unknown` are state-only; only the validated smile cue may request the separately owned happy sound. User speech cancellation and voice playback receipts belong to the backend/voice contract, not this module.

## Single-camera integration, not a second producer

The existing runner supports `--mode face` while keeping hand mode as the default. An eventual approved replacement of the existing producer can use:

```powershell
python tools/run_pet_vision.py --mode face --provider pet_vision.ipc:leased_opencv_frames --model .runtime/models/face_landmarker.task --seconds 60
```

This command is documented, not executed in this phase. Do not run it alongside an existing camera producer. Add `--send` only under the coordinated deployment authorization; it uses the existing vision-role token and metadata-only sink. `Pipeline` accepts this detector/engine directly; an async backend must collect returned events and await them in its own event loop. No actuator or TTS is owned here.

## Evidence and remaining stages

Synthetic `FaceSample` coefficient fixtures test state rules; they are not facial images and do not prove recognition accuracy. The real official model also passes a blank-image test with no face detected. No human smile, live video face quality or smile-to-real-audio outcome has been verified.

The next increments are visible open-mouth smiling/laugh-like cues (without claiming audible laughter), conservative `possible_crying` candidates, and deliberate-looking playful facial configurations. Crying and playful rules are not implemented in this first fixed delivery, and ordinary face motion will not be labeled an emotion.

Official sources: [Face Landmarker Python API guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python), [model bundle and model cards](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker), [official Python sample](https://github.com/google-ai-edge/mediapipe-samples/blob/main/examples/face_landmarker/python/%5BMediaPipe_Python_Tasks%5D_Face_Landmarker.ipynb). Blendshape values are coefficients; upstream describes their use for facial rendering. The project-specific rule thresholds above are not supplied or validated by Google. Consult upstream model/package licenses; no model weights or example media are redistributed in Git.

# Face size: dataset rejection versus Reachy camera framing

## Independent diagnostic run, 2026-09-24

The second run used the same fixed 256 GENKI samples, model, coefficients and quality thresholds as GENKI_EVALUATION.md. It added only image dimensions and transient face-size metadata to the ignored JSON `.runtime/genki-smile-scale-analysis.json`. It reproduced TP65/FP0/TN71/FN7, unknown positive56/negative57, coverage143/256 and all-positive response recall65/128. No training or threshold changes occurred.

This new run recorded detector source SHA256 `797525d9fe087e7331fab2215e54922367db30aeb0d4c8058d5ef13ec344d7d0` and took 13.016 seconds. The first run's JSON remains unchanged and lacks this source-hash field; this second record does not retroactively attest the first run. Raw archive/images remained in memory and are not committed.

Of 256 images, 95 had `face_too_small` (50 smile, 45 non-smile). Their median original image size was 179x192; median minimum face-box dimension was 71.4 pixels, with range35.4–79.4 and interquartile range65.45–75.05. Their median face width occupied39.9% of image width and height42.7% of image height. The whole sample's median image size was180x192; detected faces had median minimum dimension84.8px. Usable143 faces had median96.8px.

These small original images often contain a prominently framed face. Their rejection is an absolute available-pixel limitation, not evidence that Reachy fails at an equivalent real-world distance. Reason counts can overlap. Do not upscale these pictures and present increased gate acceptance as recovered visual detail or generalization improvement.

## Current camera path and distance limits

Read-only inspection of `tools/run_pet_vision_camera.py` shows a1920x1080 DirectShow capture resized to640x360 before inference. The detector requires BOTH box dimensions at least80px. Under this uniform resize, this corresponds to BOTH raw dimensions at least240px, or at least12.5% of frame width and22.22% of frame height. Source resolution must still be verified from actual returned frames in a future authorized live session.

| Inference dimensions | Fixed minimum face dimension | Equivalent1920x1080 source dimension |
|---|---:|---:|
|640x360 current|80px|240px|
|960x540 proposed offline candidate|80px|160px|
|1280x720 possible later candidate|80px|120px|

Larger inference frames may preserve detail already present in a true high-resolution source; they also cost computation. They do not guarantee detection, acceptable blur/exposure, or event latency. No runtime resolution change is made here.

The read-only daemon camera-spec endpoint exposes K with principal point approximately(1906,1328). Installed SDK `camera_base.py` explicitly treats the reference size as3840x2592 and rescales with crop factors. Applying that K directly to640x360 or1920x1080 would be incorrect. The DirectShow crop/actual framing and physical face dimensions have not been calibrated. Consequently no reliable distance in meters is claimed. With fixed lens/crop, projected face size is approximately inversely proportional to distance, but pixel thresholds alone do not establish a tested operating distance.

## Prospective offline experiment (not yet executed)

1. Freeze the original bilateral smile threshold .55,80px gate, remaining quality settings, model hash and800ms temporal rule before opening new validation outcomes. Compare only640x360 versus960x540 initially; retain the current runtime until evidence supports a change.
2. Use genuinely higher-resolution, authorized face imagery, with source dimensions at least960x540. Preserve aspect ratio, document cropping, and use identical input content for both arms. GENKI's small originals are unsuitable for testing restored high-resolution detail. Do not create detail by enlarging them.
3. Reserve a GENKI static-rule holdout by excluding all first256 IDs, then selecting128 per label with seed20260925. Keep that separate from the high-resolution experiment: it checks unchanged static smile behavior and cannot validate Reachy distance or temporal rules. Record the split before inference; do not tune against its results.
4. In the high-resolution set, stratify by true source face dimensions below160,160–239 and at least240px, and annotate smile/non-smile plus ambiguous cases before inference. Separate people/sessions between exploratory and acceptance sets. Report TP/FP/FN/TN, positive/negative unknown separately, coverage, all-positive response recall, and reasons by size bin. A larger frame passing the size gate alone is not a successful recognition outcome.
5. On the actual runtime hardware, measure inference and source-frame age, including p50/p95 latency and expired/dropped observations, against the existing .75s freshness limit. Static repeat images cannot validate800ms stability. Real consented video sequences and independently observed labels are needed for that stage; keep pixels transient unless separately authorized.
6. Pre-register acceptance limits and dataset sufficiency before collecting the high-resolution acceptance set. If results motivate threshold changes, use a further untouched set rather than relabeling this evaluation as improved generalization.

No camera was opened for this analysis. Crying/playful recognition and live voice response remain outside its evidence.

## Executed native-resolution availability check

Following the coordinator's request, `tools/inspect_genki_resolution.py` downloaded the same pinned official archive into memory and decoded all4000 images only to inspect dimensions. It reproduced the original seed20260924 exclusion set of256 IDs. Among the remaining3744, maximum width was972 and maximum height480; **zero smile and zero non-smile images satisfy native width>=960 AND height>=540**. Full size metadata is in ignored `.runtime/genki-resolution-census.json`; no images/archive were written. This was a complete availability census, not another inference run on the first256.

GENKI is the official source whose evaluation use had been checked in this task. Other mentioned datasets have not been cleared/acquired here; this result is not a claim that no suitable dataset exists anywhere. The permitted available source cannot support the proposed paired experiment. **There is currently no measured evidence that960 improves recognition, and no measured960-versus640 latency cost on real face inputs.** Raising resolution remains an unvalidated candidate. Production is unchanged.

## Reproducible offline evaluator for future authorized native inputs

`tools/run_pet_vision_resolution_eval.py` accepts a local manifest of untouched, already authorized native images with independent0/1 smile labels. It opens no camera. Manifest format (paths relative to its directory):

```json
[{"id":"sessionA-frame001","label":1,"path":"native-frame001.jpg"}]
```

Supply at least32 unique smile and32 unique non-smile images; this is a descriptive pilot size, not a safety or statistical acceptance guarantee. Separate people/sessions from exploratory material, avoid correlated adjacent-frame sampling, and confirm files are native rather than previously enlarged. The tool can enforce dimensions and duplicate content, but cannot establish consent, native provenance or independence from pixel dimensions alone. Ambiguous expressions should not be forced into binary ground truth.

```powershell
python tools/inspect_genki_resolution.py
python tools/run_pet_vision_resolution_eval.py --manifest .runtime/authorized-native/manifest.json --model .runtime/models/face_landmarker.task --output .runtime/resolution-pilot-01.json
```

Before inference, the evaluator fixes32 per class with seed20260925 and writes a separate immutable preregistration with sample hashes, source sizes, crop coordinates, model/detector/evaluator hashes and unchanged thresholds. It rejects insufficient dimensions without inference. Both arms use exactly the same centered16:9 crop and production-default linear resize to640x360 and960x540, never upsampling. Processing order alternates between arms after blank warmups. A frame cropped from a non16:9 image is a paired offline comparison, not a replication of the DirectShow camera framing.

The result reports confusion counts, positive/negative unknown, coverage, all-positive recall, quality reasons and per-sample outcomes for both arms. Timing includes inference and separately resize+inference p50/p95 and counts exceeding750ms. These timings exclude capture, decoding and transport; they cannot establish live source age, expiry rate or800ms stability. No production events or media outputs are emitted. Outputs remain under ignored `.runtime`; an existing run filename cannot be overwritten.

Validation completed:14 focused tests passed, including rejection of972x480/959x540/960x539 inputs and matched centered crop geometry. The real model processed a synthetic blank1920x1080 frame at both640 and960; both returned unknown/no-face. The CLI's insufficient-sample path returned eligible negative1/positive0 and `inference_performed:false`. These are implementation checks, not facial-recognition or latency evidence. No high-resolution labeled face set was available, so a paired facial experiment was deliberately not fabricated.

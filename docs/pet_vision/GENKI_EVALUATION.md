# GENKI-4K: first bounded smile evaluation

Evaluated on 2026-09-24 using the frozen first face implementation `fa36babe907dc155d8f5401cf83c678adb9c19ea`. **This is a static smile-label evaluation, not a video, sustained-800-ms, camera, crying, playfulness or voice-output validation.** No training or threshold tuning was performed.

## Source and rights

The official [MPLab GENKI database page](https://mplab.ucsd.edu/398/) supplies 4,000 smile/non-smile images and requests attribution. Its public-use statement and archive README were checked before evaluation. There is no named standard license or explicit commercial-use grant in the material inspected; commercial rights are **not established**. The site archive is historical. This local evaluation does not imply permission to redistribute its face images or include them in a commercial product.

Attribution: **http://mplab.ucsd.edu, The MPLab GENKI-4K Dataset.**

The [official archive](https://mplab.ucsd.edu/398/media/genki4k.tar) is 29,255,680 bytes (below the script's 32 MiB hard cap), SHA256 `74776c0a3fac07f1cefc5d8acebf55a71fc870babc68c6b044a87d811b6de999`. It was fetched into memory; only selected JPEG entries were decoded. The tar and images were not persisted, committed or uploaded. Local sample-level labels, coefficients and quality reasons are ignored runtime metadata; this report publishes aggregate counts only.

## Preregistered selection and settings

- Uniform random sample without replacement, 128 positive + 128 negative images, Python 3.12 random seed `20260924`; indices are sorted only for processing order.
- Original image dimensions, no image upscaling or crop substitution.
- MediaPipe 1.0.1 official face model, SHA256 `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.
- Configured detector floor 0.7; a positive static cue requires both mouthSmile coefficients >= 0.55.
- Unchanged quality thresholds: face minimum dimension 80 px, mean grayscale 35–225, Laplacian variance >=25, no face clipping within 1% image border, abs yaw <=35 degrees, abs pitch <=30 degrees; exactly one detected face.
- No repeated-static-image pseudo-video is constructed. No production event, audio or robot action is sent by this evaluator.

## Results: preserve the unknown denominator

| Frozen quality gate | Smile label, n=128 | Non-smile label, n=128 |
| --- | ---: | ---: |
| Predict smile | TP 65 | FP 0 |
| Predict non-smile | FN 7 | TN 71 |
| Unknown / quality rejection | 56 | 57 |

- Coverage: **143/256 = 55.86%**; rejection/unknown: 113/256 = 44.14%.
- Among decided positives, recall: 65/(65+7) = 90.28%; FN rate: 7/72 = 9.72%.
- Among decided negatives, observed false-positive rate: 0/(0+71) = 0%. This small sample does not establish a true zero false-positive rate.
- Across **all** sampled positive images, response recall is only **65/128 = 50.78%**. There are 63 missed-or-unknown positive samples, 49.22% of all positives.
- Across all sampled negatives, observed false-response rate is 0/128; the 57 unknown negatives are not counted as true negatives.

Reasons counted per image (an image may have multiple reasons): face_too_small 95, no_face 7, face_clipped 7, exposure 2, blur_or_low_texture 3. Small input faces dominate the loss of coverage. This is a real usability limitation in this dataset, not evidence that those images were negative or that the user would not be smiling.

Diagnostic calculation using the same already-computed coefficients **without** the quality gate: 249/256 decided, TP109/FN15/FP1/TN124, four positive and three negative no-face cases. This yields 109/128=85.16% response recall across all positives, and 1/128=0.78% false responses across all negatives (1/125=0.80% among decided negatives). This is diagnostic only: the runtime quality gate was not removed, and this result must not be substituted for the deployed-rule result.

No accuracy comparison with other models is claimed. The sample is small and balanced by design, unlike deployment prevalence; image independence, upstream model training overlap, domain shift and temporal behavior are not established. A new held-out set and actual Reachy frames are required before changing thresholds or claiming field performance.

## Reproduce without raw-media persistence

```powershell
python tools/run_pet_vision_face_setup.py
python tools/run_pet_vision_genki_eval.py --per-class 128
python -m pytest tests/test_pet_vision_evaluation.py tests/test_pet_vision_face.py -q
```

The script pins the archive hash, sample seed, static threshold and quality settings. It records model/source hashes and metrics in ignored `.runtime/genki-smile-evaluation.json`. It permits at most 512 samples per class and only writes evaluation metadata below the worktree `.runtime`. Metric unit tests explicitly prevent unknowns from becoming true negatives and verify both decided-only and full-denominator rates. The combined metric+face tests passed 12/12 locally with the real face model present.

## Other candidates checked, not downloaded or used

- [AffectNet official page](https://www.mohammadmahoor.com/pages/databases/affectnet/) and [academic-use agreement](https://mohammadmahoor.com/wp-content/uploads/2024/06/AffectNet-Agreement-v2.1-10May2024.pdf): research/academic access terms, not a blanket commercial grant. Not downloaded, trained on or evaluated here.
- DISFA: [official agreement](https://mohammadmahoor.com/wp-content/uploads/2016/11/DISFA_agreement_2016.pdf) requires research/development use and prohibits redistribution; [authors' paper](https://mohammadmahoor.com/wp-content/uploads/2017/06/DiSFA_Paper_andAppendix_Final_OneColumn1-1.pdf) describes participant consent for non-commercial research. Action-unit labels could help evaluate facial movements, but are not crying labels. Not downloaded or used here.
- [RAF-DB authors' paper](https://www.whdeng.cn/RAF/li_RAFDB_2017_CVPR.pdf) was located; the dataset page did not load during this check, so current access/commercial terms were not verified. Not downloaded or used here.

No verified crying or deliberate-playfulness dataset has been used. Sadness labels do not replace crying ground truth; facial puckering does not establish playful intent. Provisional heuristic expansion was paused on a separate worktree branch when data evaluation became the priority; it is not part of the frozen smile delivery.

"""Offline paired resolution evaluation of explicitly supplied, labeled native images.

Manifest: [{"id":"sample-001", "label":1, "path":"native-image.jpg"}, ...].
Use authorized images from an untouched acceptance set, not generated/upscaled
images. Relative paths resolve against the manifest. This tool never captures,
saves, uploads or emits images or production events. Results stay in .runtime.
"""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pet_vision.face_detector import MediaPipeFaceDetector, QualityThresholds
from run_pet_vision_genki_eval import confusion, THRESHOLD

SEED = 20260925
PER_CLASS = 32  # Descriptive pilot, not a statistical safety acceptance claim.


def paired_frames(frame):
    """Identical centered 16:9 content; downsample only, never stretch/upscale."""
    import cv2
    height, width = frame.shape[:2]
    units = min(width // 16, height // 9)
    if units < 60:
        raise ValueError('Native centered 16:9 crop must be at least 960x540')
    crop_width, crop_height = 16 * units, 9 * units
    x, y = (width - crop_width)//2, (height - crop_height)//2
    crop = frame[y:y+crop_height, x:x+crop_width]
    return {w:cv2.resize(crop, (w, w*9//16), interpolation=cv2.INTER_LINEAR)
            for w in (640, 960)}, dict(x=x, y=y, width=crop_width, height=crop_height)


def outcome(observation, label):
    single = len(observation.faces) == 1
    face = observation.faces[0] if single else None
    reasons = list(observation.frame_quality.get('reasons', []))
    reasons += (face.quality.get('reasons', []) if face else
                ['no_face' if not observation.faces else 'multiple_faces'])
    return dict(label=label, single_face=single, quality_usable=not reasons,
                quality_reasons=sorted(set(reasons)),
                face_pixels=face.quality.get('face_pixels') if face else None,
                smile_left=face.coefficients.get('mouthSmileLeft', 0.) if face else None,
                smile_right=face.coefficients.get('mouthSmileRight', 0.) if face else None)


def main():
    import cv2
    import numpy as np
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--model', default='.runtime/models/face_landmarker.task')
    parser.add_argument('--output', default='.runtime/resolution-paired-evaluation.json')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = Path(args.output).resolve()
    if not target.is_relative_to(root/'.runtime'):
        parser.error('Output must be under this worktree .runtime')
    prereg = target.with_suffix('.preregistered.json')
    if target.exists() or prereg.exists():
        parser.error('Use a fresh output name; existing run records are immutable')
    manifest = Path(args.manifest).resolve()
    entries = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(entries, list) or not 1 <= len(entries) <= 512:
        parser.error('Manifest must contain 1..512 labeled native images')
    seen_ids, seen_hashes, candidates, rejected = set(), set(), [], []
    for entry in entries:
        sample_id, label = entry['id'], entry['label']
        if not isinstance(sample_id, str) or not sample_id or sample_id in seen_ids or type(label) is not int or label not in (0, 1):
            parser.error('Unique nonempty IDs and integer labels 0/1 required')
        seen_ids.add(sample_id)
        path = (manifest.parent/entry['path']).resolve()
        if path.stat().st_size > 10*1024*1024:
            parser.error('Each source image must be at most10MiB')
        content = path.read_bytes()
        digest = sha256(content).hexdigest()
        if digest in seen_hashes:
            parser.error('Duplicate image content is not an independent sample')
        seen_hashes.add(digest)
        frame = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[0]*frame.shape[1] > 16_000_000:
            parser.error('Undecodable or over16MP source image')
        try:
            _, crop = paired_frames(frame)
        except ValueError:
            rejected.append(sample_id)
            continue
        candidates.append(dict(id=sample_id, label=label, sha256=digest, crop=crop,
                               source_width=frame.shape[1], source_height=frame.shape[0], path=path))
    counts = {str(y):sum(e['label']==y for e in candidates) for y in (0, 1)}
    if min(counts.values()) < PER_CLASS:
        print(json.dumps(dict(status='insufficient_native_samples', eligible_by_label=counts,
                              required_per_class=PER_CLASS, rejected_ids=rejected, inference_performed=False)))
        return
    rng = random.Random(SEED)
    selected = [e for y in (0, 1) for e in rng.sample(sorted([e for e in candidates if e['label']==y], key=lambda e:e['id']), PER_CLASS)]
    rng.shuffle(selected)
    registration = dict(seed=SEED, per_class=PER_CLASS, widths=[640,960], threshold=THRESHOLD,
                        quality_thresholds=asdict(QualityThresholds()), temporal_validation=False,
                        model_sha256=sha256(Path(args.model).read_bytes()).hexdigest(),
                        detector_sha256=sha256((root/'pet_vision/face_detector.py').read_bytes()).hexdigest(),
                        evaluator_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                        manifest_sha256=sha256(manifest.read_bytes()).hexdigest(),
                        samples=[{k:v for k,v in e.items() if k!='path'} for e in selected],
                        limitations='Static descriptive pilot. Does not establish camera freshness, temporal accuracy, operating distance or dataset independence.')
    target.parent.mkdir(parents=True, exist_ok=True)
    prereg.write_text(json.dumps(registration, indent=2), encoding='utf-8')
    detector = MediaPipeFaceDetector(args.model)
    rows = {640:[], 960:[]}
    try:
        for width in (640,960):
            detector.detect(np.zeros((width*9//16,width,3), dtype=np.uint8), 0.)
        for index, entry in enumerate(selected):
            content = entry['path'].read_bytes()
            if sha256(content).hexdigest() != entry['sha256']:
                raise RuntimeError('Source changed after preregistration')
            frame = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
            for width in ((640,960) if index%2==0 else (960,640)):
                crop = entry['crop']
                started = time.perf_counter()
                native = frame[crop['y']:crop['y']+crop['height'], crop['x']:crop['x']+crop['width']]
                resized = cv2.resize(native,(width,width*9//16),interpolation=cv2.INTER_LINEAR)
                detect_start = time.perf_counter()
                observation = detector.detect(resized,float(index+1))
                ended = time.perf_counter()
                row = outcome(observation,entry['label'])
                row.update(id=entry['id'], inference_ms=(ended-detect_start)*1000,
                           resize_and_inference_ms=(ended-started)*1000)
                rows[width].append(row)
    finally:
        detector.close()
    summaries = {}
    for width, values in rows.items():
        reasons = {}
        for row in values:
            for reason in row['quality_reasons']:
                reasons[reason] = reasons.get(reason,0)+1
        summaries[width] = dict(metrics=confusion(values,quality_gate=True), quality_reasons=reasons,
                               latency_ms={field:dict(zip(('p50','p95'),np.percentile([r[field] for r in values],[50,95]).tolist()))
                                           for field in ('inference_ms','resize_and_inference_ms')},
                               over_750ms=sum(r['resize_and_inference_ms']>750 for r in values))
    result = dict(registration=registration, summaries=summaries, rows=rows,
                  camera_opened=False, production_changed=False,
                  latency_scope='Offline resize+detect only; excludes capture, transport and source age. No live TTL claim.')
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(summaries,indent=2))


if __name__ == '__main__':
    main()

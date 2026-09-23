"""Bounded, static GENKI-4K evaluation; no camera, training or raw-image output.

Official source permits public use and requests acknowledgment. Commercial
rights are not established here. Downloads at most 32 MiB into memory, decodes
only the deterministic balanced sample, and persists metrics/coefficients only
under ignored .runtime. Never interprets a static image as an 800 ms video.
"""
import argparse
from dataclasses import asdict
from hashlib import sha256
import io
import json
from pathlib import Path
import random
import sys
import tarfile
import time
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pet_vision.face_detector import MediaPipeFaceDetector,QualityThresholds

URL='https://mplab.ucsd.edu/398/media/genki4k.tar'
ARCHIVE_SHA256='74776c0a3fac07f1cefc5d8acebf55a71fc870babc68c6b044a87d811b6de999'
MAX_BYTES=32*1024*1024
THRESHOLD=.55
SEED=20260924


def confusion(rows,*,quality_gate):
    out=dict(tp=0,fp=0,tn=0,fn=0,unknown_positive=0,unknown_negative=0)
    for row in rows:
        label=row['label']
        decided=row['single_face'] and (row['quality_usable'] or not quality_gate)
        if not decided:
            out['unknown_positive' if label else 'unknown_negative']+=1
            continue
        predicted=row['smile_left']>=THRESHOLD and row['smile_right']>=THRESHOLD
        out['tp' if label and predicted else 'fn' if label else 'fp' if predicted else 'tn']+=1
    positives=sum(r['label']==1 for r in rows)
    negatives=len(rows)-positives
    decided=sum(out[k] for k in ('tp','fp','tn','fn'))
    divide=lambda a,b:round(a/b,6) if b else None
    return dict(**out,sampled_positive=positives,sampled_negative=negatives,
                decided=decided,coverage=divide(decided,len(rows)),
                precision=divide(out['tp'],out['tp']+out['fp']),
                recall_on_decided=divide(out['tp'],out['tp']+out['fn']),
                false_positive_rate_on_decided=divide(out['fp'],out['fp']+out['tn']),
                response_recall_on_all_positive=divide(out['tp'],positives),
                false_response_rate_on_all_negative=divide(out['fp'],negatives),
                missed_or_unknown_positive=out['fn']+out['unknown_positive'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',default='.runtime/models/face_landmarker.task')
    parser.add_argument('--per-class',type=int,default=128)
    parser.add_argument('--output',default='.runtime/genki-smile-evaluation.json')
    args=parser.parse_args()
    if not 1<=args.per_class<=512:
        parser.error('Bounded sample must be 1..512 per class')
    target=Path(args.output).resolve()
    runtime=(Path(__file__).resolve().parents[1]/'.runtime').resolve()
    if not target.is_relative_to(runtime):
        parser.error('Evaluation metadata must stay under this worktree ignored .runtime')
    import cv2
    import numpy as np
    start=time.monotonic()
    print('Downloading bounded official archive into memory; images will not be written',flush=True)
    with urlopen(URL,timeout=30) as response:
        content=response.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES:
        raise RuntimeError('Archive exceeds 32 MiB bound')
    if sha256(content).hexdigest()!=ARCHIVE_SHA256:
        raise RuntimeError('Official archive changed; review metadata before evaluating')
    archive=tarfile.open(fileobj=io.BytesIO(content),mode='r:')
    readme=archive.extractfile('README').read().decode('utf-8')
    labels=[int(line.split()[0]) for line in archive.extractfile('labels.txt').read().decode('utf-8').splitlines() if line.strip()]
    if len(labels)!=4000 or set(labels)!={0,1} or 'acknowledge' not in readme:
        raise RuntimeError('Unexpected dataset metadata; stop before evaluation')
    rng=random.Random(SEED)
    selection=sorted(rng.sample([i+1 for i,y in enumerate(labels) if y==0],args.per_class)
                     +rng.sample([i+1 for i,y in enumerate(labels) if y==1],args.per_class))
    rows=[]
    detector=MediaPipeFaceDetector(args.model)
    try:
        for n,index in enumerate(selection,1):
            member=archive.getmember(f'files/file{index:04d}.jpg')
            if not member.isfile() or member.size>2*1024*1024:
                raise RuntimeError('Unexpected sample size/type')
            encoded=archive.extractfile(member).read()
            frame=cv2.imdecode(np.frombuffer(encoded,dtype=np.uint8),cv2.IMREAD_COLOR)
            if frame is None:
                raise RuntimeError(f'Cannot decode sample {index}')
            observation=detector.detect(frame,float(n))
            single=len(observation.faces)==1
            face=observation.faces[0] if single else None
            reasons=list(observation.frame_quality.get('reasons',[]))
            if not single:
                reasons.append('no_face' if not observation.faces else 'multiple_faces')
            elif face:
                reasons.extend(face.quality.get('reasons',[]))
            rows.append(dict(sample_id=index,label=labels[index-1],single_face=single,
                             image_width=int(frame.shape[1]),image_height=int(frame.shape[0]),
                             face_pixels=face.quality.get('face_pixels') if face else None,
                             face_width_fraction=(face.bbox[2]-face.bbox[0]) if face else None,
                             face_height_fraction=(face.bbox[3]-face.bbox[1]) if face else None,
                             quality_usable=not reasons,quality_reasons=sorted(set(reasons)),
                             smile_left=face.coefficients.get('mouthSmileLeft',0.) if face else None,
                             smile_right=face.coefficients.get('mouthSmileRight',0.) if face else None))
            if n%32==0:
                print(json.dumps({'evaluated':n,'total':len(selection)}),flush=True)
    finally:
        detector.close()
        archive.close()
    reasons={}
    for row in rows:
        for reason in row['quality_reasons']:
            reasons[reason]=reasons.get(reason,0)+1
    summary=dict(dataset='The MPLab GENKI-4K Dataset',source_url=URL,archive_bytes=len(content),
                 archive_sha256=sha256(content).hexdigest(),model_sha256=sha256(Path(args.model).read_bytes()).hexdigest(),
                 sample_count=len(selection),selection='balanced uniform random without replacement, sorted for evaluation',
                 detector_source_sha256=sha256((Path(__file__).resolve().parents[1]/'pet_vision/face_detector.py').read_bytes()).hexdigest(),
                 seed=SEED,threshold=THRESHOLD,quality_thresholds=asdict(QualityThresholds()),
                 temporal_validation=False,training_performed=False,commercial_rights='not established',
                 gated=confusion(rows,quality_gate=True),ungated_diagnostic=confusion(rows,quality_gate=False),
                 quality_reason_counts=reasons,elapsed_seconds=round(time.monotonic()-start,3))
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(dict(summary=summary,rows=rows),indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__': main()

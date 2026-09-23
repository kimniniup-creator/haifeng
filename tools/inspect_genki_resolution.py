"""Read-only image-size census of the pinned official archive; no inference/media output."""
import io
import json
from pathlib import Path
import random
import tarfile
from hashlib import sha256
from urllib.request import urlopen
from run_pet_vision_genki_eval import URL, ARCHIVE_SHA256, MAX_BYTES, SEED


def main():
    import cv2
    import numpy as np
    with urlopen(URL, timeout=30) as response:
        content = response.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES or sha256(content).hexdigest() != ARCHIVE_SHA256:
        raise RuntimeError('Archive size/hash changed')
    rows = []
    with tarfile.open(fileobj=io.BytesIO(content), mode='r:') as archive:
        labels = [int(x.split()[0]) for x in archive.extractfile('labels.txt').read().decode().splitlines() if x.strip()]
        if len(labels) != 4000 or set(labels) != {0, 1}:
            raise RuntimeError('Unexpected labels')
        rng = random.Random(SEED)
        excluded = set(rng.sample([i+1 for i,y in enumerate(labels) if y == 0], 128)
                       + rng.sample([i+1 for i,y in enumerate(labels) if y == 1], 128))
        for index, label in enumerate(labels, 1):
            member = archive.getmember(f'files/file{index:04d}.jpg')
            if not member.isfile() or member.size > 2*1024*1024:
                raise RuntimeError('Unexpected image entry')
            frame = cv2.imdecode(np.frombuffer(archive.extractfile(member).read(), dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                raise RuntimeError(f'Cannot decode {index}')
            height, width = frame.shape[:2]
            rows.append(dict(sample_id=index, label=label, width=width, height=height,
                             excluded=index in excluded, eligible=width >= 960 and height >= 540))
    remaining = [r for r in rows if not r['excluded']]
    result = dict(source_url=URL, archive_sha256=ARCHIVE_SHA256, total=len(rows), excluded=len(excluded),
                  remaining=len(remaining), requirement='native width >=960 AND height >=540; no upsampling',
                  max_width=max(r['width'] for r in remaining), max_height=max(r['height'] for r in remaining),
                  eligible_by_label={str(y):sum(r['eligible'] and r['label']==y for r in remaining) for y in (0,1)},
                  inference_performed=False, raw_media_saved=False, rows=rows)
    target = Path(__file__).resolve().parents[1]/'.runtime/genki-resolution-census.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}, indent=2))


if __name__ == '__main__':
    main()

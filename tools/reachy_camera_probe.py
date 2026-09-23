"""Local camera statistics only; child process hard deadline; no image saved."""
import sys, subprocess, json
from pathlib import Path
if '--child' not in sys.argv:
    result=Path(__file__).resolve().parents[1]/'.runtime/camera-audit.json'
    try:
        subprocess.run([sys.executable,__file__,'--child'],timeout=25,check=True)
    except subprocess.TimeoutExpired:
        result.write_text(json.dumps({'error':'Camera native call/shutdown exceeded 25 seconds; probe child terminated'}))
        print(result.read_text())
    raise SystemExit()
import json
from pathlib import Path
from reachy_mini.media.device_detection import get_video_device
from gi.repository import Gst
Gst.init(None)
name,spec=get_video_device();print(name,flush=True)
assert name and 'reachy' in name.lower()
p=Gst.parse_launch('mfvideosrc device-name="'+name+'" num-buffers=20 ! video/x-raw,format=YUY2,width=1920,height=1080,framerate=5/1 ! videoconvert ! video/x-raw,format=BGR ! appsink name=probe sync=false')
r={'device':name}
try:
 p.set_state(Gst.State.PLAYING);sample=p.get_by_name('probe').emit('try-pull-sample',8*Gst.SECOND)
 for _ in range(9):
  next_sample=p.get_by_name('probe').emit('try-pull-sample',Gst.SECOND)
  if next_sample:sample=next_sample
  else:break
 if sample:
  b=sample.get_buffer();r.update(caps=sample.get_caps().to_string(),bytes=b.get_size());ok,m=b.map(Gst.MapFlags.READ)
  if ok:
   import numpy as np
   x=np.frombuffer(m.data,dtype=np.uint8);r.update(mean=float(x.mean()),std=float(x.std()));b.unmap(m)
 else:r['error']='No sample within 8 seconds'
finally:p.set_state(Gst.State.NULL)
Path('.runtime/camera-audit.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

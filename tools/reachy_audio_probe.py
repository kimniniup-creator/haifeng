"""Bounded local SDK microphone/speaker probe. No environment audio is saved."""
import json,time,wave
from pathlib import Path
import numpy as np
from reachy_mini.media.device_detection import get_audio_device
from reachy_mini.media.audio_gstreamer import GStreamerAudio
from gi.repository import Gst
Gst.init(None)
root=Path(__file__).resolve().parents[1]/'.runtime'
src,sink=get_audio_device('Source'),get_audio_device('Sink')
if not src or not sink:raise SystemExit('Reachy endpoint missing; refuse fallback')
r={'source':src,'sink':sink,'audibility':'unverified','samples':{}}
a=GStreamerAudio()
def capture(seconds):
 parts=[];end=time.monotonic()+seconds
 while time.monotonic()<end:
  x=a.get_audio_sample()
  if x is not None:parts.append(x)
  time.sleep(.01)
 if not parts:return {'chunks':0}
 x=np.concatenate(parts)
 return {'chunks':len(parts),'shape':list(x.shape),'rms':float(np.sqrt(np.mean(x*x))),'peak':float(np.max(np.abs(x))),'nonzero':int(np.count_nonzero(x))}
try:
 a.start_recording();r['samples']['baseline']=capture(1)
 for ch in (0,1):
  t=np.arange(48000)/48000;x=np.zeros((48000,2),dtype=np.int16);x[:,ch]=(np.sin(2*np.pi*(660+ch*220)*t)*4500).astype(np.int16)
  p=root/f'probe-channel-{ch}.wav'
  with wave.open(str(p),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000);w.writeframes(x.tobytes())
  a.play_sound(str(p));r['samples'][f'channel{ch}']=capture(1.3)
  msg=a._playbin.get_bus().timed_pop_filtered(2*Gst.SECOND,Gst.MessageType.ERROR|Gst.MessageType.EOS)
  r[f'bus{ch}']=str(msg.type) if msg else 'no bus message'
 a.stop_recording()
finally:a.stop_playing();a.cleanup()
(root/'audio-local-probe.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

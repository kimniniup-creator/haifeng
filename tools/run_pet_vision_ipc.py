"""Bounded native SDK shared-camera reader. Never opens a physical device.

Run with native SDK Python. Default output is statistics only. --pipe is an
internal local child-process transport consumed by pet_vision.ipc.frames.
"""
import argparse
import json
import struct
import sys
import time
import threading
import os
from urllib.request import urlopen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=float,default=10.)
    parser.add_argument('--pipe',action='store_true')
    parser.add_argument('--direct-camera-owner-approved',action='store_true',
                        help='ONLY after media owner grants exclusive raw video lease; daemon must stay released')
    parser.add_argument('--device-name',help='Explicit verified Windows Reachy camera name; bypasses SDK enumeration')
    args=parser.parse_args()
    if not 0 < args.seconds <= 60:
        parser.error('seconds must be in (0,60]')
    # Refuse unavailable/released media; never acquire it on another owner's behalf.
    with urlopen('http://127.0.0.1:8000/api/media/status',timeout=2) as response:
        status=json.load(response)
    if args.direct_camera_owner_approved and not status.get('released'):
        raise SystemExit('Raw video requires released official media and explicit owner lease')
    if not args.direct_camera_owner_approved and (status.get('released') or not status.get('available')):
        raise SystemExit('Shared media unavailable/released; no reader opened')
    # Native Gst state transitions can block if the source disappears. This
    # process owns only the reader; its hard exit lets the OS release its handles.
    def hard_timeout():
        print('Reader hard timeout; exiting own process only',file=sys.stderr,flush=True)
        os._exit(124)
    watchdog=threading.Timer(args.seconds+15,hard_timeout)
    watchdog.daemon=True
    watchdog.start()
    from reachy_mini.media.camera_gstreamer import GStreamerCamera, Gst
    print('Video reader imports ready',file=sys.stderr,flush=True)
    if args.direct_camera_owner_approved:
        from reachy_mini.media.device_detection import get_video_device
        Gst.init([])
        name=args.device_name
        if not name:
            name,_=get_video_device()
        print('Video device enumeration finished',file=sys.stderr,flush=True)
        if not name or 'reachy' not in name.lower():
            raise SystemExit('No verified Reachy video device')
        class VideoOnlyReader:
            def __init__(self):
                self.pipeline=Gst.parse_launch(
                    'mfvideosrc name=source ! video/x-raw,format=YUY2,width=1920,height=1080,framerate=5/1 '
                    '! videoconvert ! videoscale ! video/x-raw,format=BGR,width=640,height=360 '
                    '! appsink name=vision sync=false drop=true max-buffers=1')
                self.pipeline.get_by_name('source').set_property('device-name',name)
                self._appsink_video=self.pipeline.get_by_name('vision')
            def open(self): self.pipeline.set_state(Gst.State.PLAYING)
            def close(self): self.pipeline.set_state(Gst.State.NULL)
        camera=VideoOnlyReader()
    else:
        camera=GStreamerCamera(log_level='ERROR')
    count=duplicates=stale=0
    last_pts=None
    shape=None
    ages=[]
    start=time.monotonic()
    try:
        print('Opening video reader',file=sys.stderr,flush=True)
        camera.open()
        print('Video reader open returned',file=sys.stderr,flush=True)
        last_status_check=0.
        while time.monotonic()-start < args.seconds:
            if time.monotonic()-last_status_check>1.:
                with urlopen('http://127.0.0.1:8000/api/daemon/status',timeout=2) as response:
                    daemon=json.load(response)
                backend=daemon.get('backend_status') or {}
                if daemon.get('error') or backend.get('error') or backend.get('control_loop_stats',{}).get('nb_error',0):
                    raise RuntimeError('Daemon error observed; stopping this reader only')
                if args.direct_camera_owner_approved and not daemon.get('media_released'):
                    raise RuntimeError('Official media acquired; stopping exclusive reader')
                last_status_check=time.monotonic()
            sample=camera._appsink_video.emit('try-pull-sample',100_000_000)
            if sample is None:
                continue
            buf=sample.get_buffer()
            if buf is None or buf.pts == Gst.CLOCK_TIME_NONE:
                stale+=1
                continue
            if last_pts is not None and buf.pts <= last_pts:
                duplicates+=1
                continue
            last_pts=buf.pts
            segment=sample.get_segment()
            running=segment.to_running_time(Gst.Format.TIME,buf.pts)
            clock=camera.pipeline.get_clock()
            if clock is None or running == Gst.CLOCK_TIME_NONE:
                stale+=1
                continue
            age=(clock.get_time()-camera.pipeline.get_base_time()-running)/Gst.SECOND
            if not -.05 <= age <= .75:
                stale+=1
                continue
            observed_at=time.time()-max(0.,age)
            caps=sample.get_caps().get_structure(0)
            width,height=caps.get_value('width'),caps.get_value('height')
            size=buf.get_size()
            if size != width*height*3:
                raise RuntimeError('Unexpected BGR stride; refusing ambiguous frame')
            count+=1
            ages.append(age)
            shape=[height,width,3]
            if args.pipe:
                header=json.dumps(dict(shape=shape,observed_at=observed_at,size=size)).encode()
                sys.stdout.buffer.write(struct.pack('!I',len(header)))
                sys.stdout.buffer.write(header)
                sys.stdout.buffer.write(buf.extract_dup(0,size))
                sys.stdout.buffer.flush()
    finally:
        camera.close()
        watchdog.cancel()
    stats=dict(frames=count,duplicates=duplicates,stale=stale,shape=shape,
               elapsed=round(time.monotonic()-start,3),
               max_age=round(max(ages),4) if ages else None)
    print(json.dumps(stats),file=sys.stderr if args.pipe else sys.stdout)
    if count == 0:
        raise SystemExit('No fresh IPC frames received; original daemon left untouched')


if __name__=='__main__':
    main()

"""Bounded Windows DirectShow-only reader for an explicitly leased Reachy camera.

Enumerates video names without opening them; opens exactly one unique matching
Reachy camera. No GStreamer, Reachy SDK, audio, recording or cloud connection.
"""
import argparse
import hashlib
import json
import os
import struct
import sys
import threading
import time
from urllib.request import urlopen


def check_owner():
    with urlopen('http://127.0.0.1:8000/api/daemon/status',timeout=2) as response:
        daemon=json.load(response)
    backend=daemon.get('backend_status') or {}
    if daemon.get('state')!='running' or not daemon.get('media_released'):
        raise RuntimeError('Raw video lease requires running daemon with media released')
    if daemon.get('error') or backend.get('error') or backend.get('control_loop_stats',{}).get('nb_error',0):
        raise RuntimeError('Daemon error; refusing/stopping this reader only')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-approved',action='store_true')
    parser.add_argument('--device-name',default='Reachy Mini Camera')
    parser.add_argument('--seconds',type=float,default=10.)
    parser.add_argument('--pipe',action='store_true')
    args=parser.parse_args()
    if not args.owner_approved or not 0<args.seconds<=60 or 'reachy' not in args.device_name.lower():
        parser.error('Explicit owner approval, Reachy name and 0<seconds<=60 required')
    check_owner()
    def timeout():
        print('DirectShow reader hard deadline; exiting own process',file=sys.stderr,flush=True)
        os._exit(124)
    watchdog=threading.Timer(args.seconds+15,timeout)
    watchdog.daemon=True
    watchdog.start()
    import cv2
    from pygrabber.dshow_graph import FilterGraph
    graph=FilterGraph()
    names=graph.get_input_devices()
    indexes=[i for i,name in enumerate(names) if name==args.device_name]
    if len(indexes)!=1:
        raise RuntimeError('Expected exactly one matching Reachy video device; none opened')
    print('Opening uniquely matched Reachy DirectShow video device',file=sys.stderr,flush=True)
    check_owner()
    cap=cv2.VideoCapture()
    count=duplicates=stale=0
    last_hash=None
    start=time.monotonic()
    shape=None
    try:
        if not cap.open(indexes[0],cv2.CAP_DSHOW):
            raise RuntimeError('Reachy DirectShow camera could not open')
        cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT,1080)
        cap.set(cv2.CAP_PROP_FPS,10)
        print(json.dumps({'backend':cap.getBackendName(),'width':cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                          'height':cap.get(cv2.CAP_PROP_FRAME_HEIGHT),'reported_fps':cap.get(cv2.CAP_PROP_FPS)}),file=sys.stderr,flush=True)
        capture_start=time.monotonic()
        last_check=0.
        while time.monotonic()-capture_start<args.seconds:
            if time.monotonic()-last_check>1:
                check_owner()
                last_check=time.monotonic()
            # Conservative read-start time; never give a slow read a fresh timestamp.
            captured=time.time()
            ok,frame=cap.read()
            if not ok:
                raise RuntimeError('Reachy video read failed; no auto-reconnect')
            if time.time()-captured>.75:
                stale+=1
                continue
            frame=cv2.resize(frame,(640,360))
            raw=frame.tobytes()
            digest=hashlib.blake2s(raw,digest_size=16).digest()
            if digest==last_hash:
                duplicates+=1
                continue
            last_hash=digest
            count+=1
            shape=list(frame.shape)
            if args.pipe:
                header=json.dumps(dict(shape=shape,observed_at=captured,size=len(raw))).encode()
                sys.stdout.buffer.write(struct.pack('!I',len(header))+header+raw)
                sys.stdout.buffer.flush()
    finally:
        cap.release()
        watchdog.cancel()
    print(json.dumps(dict(frames=count,duplicates=duplicates,stale=stale,shape=shape,
                          elapsed=round(time.monotonic()-start,3),capture_seconds=round(time.monotonic()-capture_start,3),
                          timestamp_basis='read_start_no_sensor_pts')),
          file=sys.stderr if args.pipe else sys.stdout,flush=True)
    if not count:
        raise SystemExit('No fresh distinct frames received')


if __name__=='__main__': main()

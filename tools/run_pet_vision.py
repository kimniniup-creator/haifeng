"""Local-only demo or owner-provided timestamped BGR provider.

Provider module:function returns an iterable of pet_vision.pipeline.Frame.
It owns opening/closing its shared reader. No raw camera option exists here.
"""
import argparse
import importlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pet_vision import GestureEngine
from pet_vision.pipeline import LocalEventSink, Pipeline
from pet_vision.synthetic import demo_observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--provider", help="module:function yielding timestamped frames")
    parser.add_argument("--seconds", type=float, help="bounded camera window, 0<seconds<=60; built-in IPC providers only")
    parser.add_argument('--continuous',action='store_true',help='persistent leased DirectShow provider only; exits on delivery/camera errors')
    parser.add_argument('--event-log',help='local metadata NDJSON log, rotated at 1 MiB with one backup; replaces stdout events')
    parser.add_argument("--model", default=".runtime/models/hand_landmarker.task")
    parser.add_argument("--send", action="store_true", help="deliver metadata to local backend (requires PET_VISION_TOKEN)")
    args = parser.parse_args()
    if bool(args.demo) == bool(args.provider):
        parser.error("choose exactly one of --demo or --provider")
    if args.seconds is not None and (not 0 < args.seconds <= 60 or not args.provider or
                                    args.provider not in ('pet_vision.ipc:frames','pet_vision.ipc:leased_video_frames','pet_vision.ipc:leased_opencv_frames')):
        parser.error('--seconds requires a built-in camera provider and 0<seconds<=60')
    if args.continuous and (args.seconds is not None or args.provider != 'pet_vision.ipc:leased_opencv_frames'):
        parser.error('--continuous requires leased_opencv_frames and cannot be combined with --seconds')
    emit = lambda value: print(json.dumps(value), flush=True)
    if args.event_log:
        import logging
        from logging.handlers import RotatingFileHandler
        log_path=Path(args.event_log)
        log_path.parent.mkdir(parents=True,exist_ok=True)
        logger=logging.getLogger('pet_vision.events')
        logger.setLevel(logging.INFO)
        logger.propagate=False
        handler=RotatingFileHandler(log_path,maxBytes=1024*1024,backupCount=1,encoding='utf-8')
        logger.addHandler(handler)
        emit=lambda value:logger.info(json.dumps(value))
    if args.send:
        delivery = LocalEventSink()
        def sink(event):
            receipt = delivery(event)
            # Only event metadata and bounded acknowledgement fields; never credentials.
            emit({'event': event, 'delivery': {k: receipt[k] for k in
                 ('status','reason','decision_id') if k in receipt}})
    else:
        sink = emit
    engine = GestureEngine()
    if args.demo:
        for obs in demo_observations(time.time()):
            # Keep acquisition timestamps real when using backend TTL validation.
            time.sleep(max(0, obs.observed_at - time.time()))
            for event in engine.update(obs, now=time.time()):
                sink(event)
        return
    from pet_vision.detector import MediaPipeDetector
    module, name = args.provider.split(":", 1)
    provider = getattr(importlib.import_module(module), name)
    detector = MediaPipeDetector(args.model)
    stream = provider(continuous=True) if args.continuous else provider(seconds=args.seconds) if args.seconds is not None else provider()
    try:
        pipeline = Pipeline(detector, engine, sink)
        for frame in stream:
            pipeline.process(frame)
    finally:
        if hasattr(stream, 'close'):
            stream.close()
        detector.close()


if __name__ == "__main__":
    main()

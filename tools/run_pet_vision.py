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
    parser.add_argument("--model", default=".runtime/models/hand_landmarker.task")
    parser.add_argument("--send", action="store_true", help="deliver metadata to local backend (requires PET_API_TOKEN)")
    args = parser.parse_args()
    if bool(args.demo) == bool(args.provider):
        parser.error("choose exactly one of --demo or --provider")
    sink = LocalEventSink() if args.send else lambda e: print(json.dumps(e), flush=True)
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
    stream = provider()
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

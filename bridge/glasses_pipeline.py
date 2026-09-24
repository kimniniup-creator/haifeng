"""Glasses shutter to robot reaction, over one held-open BLE link.

    glasses ──BLE──> this process ──vision model──> emotion ──REST──> Reachy

`run` keeps the link open and reacts to whatever the glasses send, including a
photo the wearer takes on the glasses themselves. `once` takes a single photo on
request, which is the quickest way to check the whole chain.
"""

import os
import sys
import time
import json
import asyncio
import logging
import argparse
from typing import Any, Dict, Sequence
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

from bridge.scene_agent import react
from bridge.luma_ble import LumaBleError
from bridge.luma_daemon import LumaSession
from bridge.m5_link import M5Link
from bridge.m5_motion import ReachyMirror


logger = logging.getLogger(__name__)

# One reaction at a time, and never two in a row on top of each other: an
# emotion move plus its audio runs for several seconds.
MIN_GAP_S = 8.0


class Pipeline:
    """Serialise photo analysis so reactions never overlap on the robot."""

    def __init__(self, out_dir: Path, with_sound: bool = True, m5: M5Link | None = None) -> None:
        """Set up output and reaction state; nothing runs until a photo arrives."""
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.with_sound = with_sound
        self.lock = asyncio.Lock()
        self.last_reaction = 0.0
        self.handled = 0
        # The pocket window laughs along; it is optional and never blocks the robot.
        self.m5 = m5

    async def handle(self, image: bytes) -> Dict[str, Any] | None:
        """Save a photo, read it, and act on it. Skips when one just ran."""
        async with self.lock:
            since = time.time() - self.last_reaction
            if since < MIN_GAP_S:
                logger.info("skipping photo: reacted %.1fs ago", since)
                return None

            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = self.out_dir / f"glasses-{stamp}.jpg"
            path.write_bytes(image)

            event_id = f"glasses-{stamp}"
            if self.m5 is not None:
                await asyncio.to_thread(self.m5.photo_received, event_id)

            started = time.time()
            try:
                result = await asyncio.to_thread(react, image, self.with_sound)
            except Exception as error:
                logger.error("analysis failed: %s", error)
                if self.m5 is not None:
                    await asyncio.to_thread(self.m5.photo_failed, event_id)
                return None

            if self.m5 is not None:
                await asyncio.to_thread(
                    self.m5.photo_replied, event_id, result["m5_expression"],
                    result["intensity"], result.get("line_zh", ""),
                )

            self.last_reaction = time.time()
            self.handled += 1
            result["image"] = str(path)
            result["seconds"] = round(time.time() - started, 1)
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"{result['emotion']} {result['intensity']:.2f} "
                f"(confidence {result['confidence']:.2f}) -> {result['move']} "
                f"in {result['seconds']}s\n"
                f"    scene: {result['scene']}\n"
                f"    says : {result['utterance']}\n"
                f"    m5   : {result.get('line_zh', '')}",
                flush=True,
            )
            return result


async def _session(args: argparse.Namespace, pipeline: Pipeline | None):
    selector = (os.getenv("LUMA_DEVICE") or "").strip() or None
    handler = None
    if pipeline is not None:

        async def handler(image: bytes) -> None:  # noqa: F811
            await pipeline.handle(image)

    session = LumaSession(selector=selector, on_image=handler)
    task = asyncio.create_task(session.run())
    return session, task


async def _shutdown(session: LumaSession, task: asyncio.Task) -> None:
    await session.stop()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def _run(args: argparse.Namespace) -> int:
    """Hold the link open and react to every photo that arrives."""
    pipeline = Pipeline(Path(args.out), with_sound=not args.no_sound, m5=_m5(args))
    session, task = await _session(args, pipeline)
    try:
        await session.wait_connected(timeout=args.timeout)
        print("Glasses linked. Press the shutter, or wait for the interval.", flush=True)
        if args.interval <= 0:
            print("Interval off: only photos the glasses push will be handled.", flush=True)
        while True:
            if args.interval > 0:
                await asyncio.sleep(args.interval)
                try:
                    image = await session.capture()
                except Exception as error:
                    logger.warning("scheduled capture failed: %s", error)
                    continue
                await pipeline.handle(image)
            else:
                await asyncio.sleep(1.0)
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 0
    except LumaBleError as error:
        logger.error("%s", error)
        return 1
    finally:
        await _shutdown(session, task)


async def _once(args: argparse.Namespace) -> int:
    """Take one photo on the glasses and drive the whole chain with it."""
    pipeline = Pipeline(Path(args.out), with_sound=not args.no_sound, m5=_m5(args))
    session, task = await _session(args, None)
    try:
        started = time.time()
        await session.wait_connected(timeout=args.timeout)
        print(f"link up in {time.time() - started:.1f}s", flush=True)
        image = await session.capture()
        print(f"photo: {len(image)} bytes", flush=True)
        result = await pipeline.handle(image)
        if result is None:
            return 1
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=1), flush=True)
        return 0
    except LumaBleError as error:
        # The glasses go off the air for minutes after a session; say so plainly
        # rather than ending the run in an asyncio traceback.
        logger.error("%s", error)
        return 1
    finally:
        await _shutdown(session, task)


def _m5(args: argparse.Namespace) -> M5Link | None:
    if args.no_m5:
        return None
    link = M5Link(os.getenv("M5_PORT") or None)
    if not getattr(args, "no_m5_motion", False):
        # Shake the M5, Reachy shakes its head: needs the port open from the start.
        link.listeners.append(ReachyMirror().handle)
        if not link.connect():
            logger.warning("M5 not found; photos still go to Reachy")
    return link


async def _replay(args: argparse.Namespace) -> int:
    """Feed a saved glasses photo through the same chain, without the BLE link."""
    pipeline = Pipeline(Path(args.out), with_sound=not args.no_sound, m5=_m5(args))
    result = await pipeline.handle(Path(args.image).read_bytes())
    if result is not None and args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1), flush=True)
    await asyncio.sleep(1.0)  # let the M5 acknowledge before the port closes
    return 0 if result is not None else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m bridge.glasses_pipeline`."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    parser = argparse.ArgumentParser(description="Glasses photo -> vision model -> Reachy")
    parser.add_argument("--out", default=".runtime/glasses", help="where photos are kept")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for the link")
    parser.add_argument("--no-sound", action="store_true", help="move only, no bundled audio")
    parser.add_argument("--json", action="store_true", help="print the full reading")
    parser.add_argument("--no-m5", action="store_true", help="leave the M5 pocket window out")
    parser.add_argument("--no-m5-motion", action="store_true", help="do not mirror M5 shakes on Reachy")
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="stay linked and react to every photo")
    run.add_argument(
        "--interval",
        type=float,
        default=0.0,
        help="seconds between automatic captures; 0 waits for the glasses to push",
    )
    subparsers.add_parser("once", help="take one photo and react to it")
    replay = subparsers.add_parser("replay", help="react to a saved photo, no glasses needed")
    replay.add_argument("image")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    runner = {"run": _run, "once": _once, "replay": _replay}[args.command]
    try:
        return asyncio.run(runner(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())

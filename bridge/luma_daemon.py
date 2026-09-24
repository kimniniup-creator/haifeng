"""Long-lived BLE link to the Luma glasses.

`luma_ble` connects, takes one photo and drops the link. Every capture therefore
pays a fresh scan, connect and handshake. This module keeps one connection open
instead, so a capture is a single write on a live link, and - if the glasses push
a file when their own shutter is pressed - images arrive with no request at all.

Whether the glasses push unsolicited files is a property of the firmware, not of
this code. Run `listen` and press the shutter to find out on real hardware; the
reassembler treats a pushed file exactly like a requested one.
"""

import os
import sys
import time
import asyncio
import logging
import argparse
from typing import Awaitable, Callable, Sequence
from pathlib import Path
from datetime import datetime, timezone

from bridge.luma_ble import (
    WRITE,
    FILE_NOTIFY,
    CONTROL_NOTIFY,
    PHOTO_SECONDS,
    CONNECT_SECONDS,
    FILE_STALL_SECONDS,
    LumaBleError,
    FileReassembler,
    discover,
    choose_device,
    command_frame,
    _decode_control,
    _find_characteristic,
)


try:
    from bleak import BleakClient
except ImportError:  # pragma: no cover - exercised only without bleak
    BleakClient = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

RECONNECT_MIN_S = 2.0
RECONNECT_MAX_S = 30.0
IDLE_POLL_S = 0.5

ImageHandler = Callable[[bytes], Awaitable[None]]


class LumaSession:
    """One glasses link held open, reconnecting on its own when it drops."""

    def __init__(
        self,
        selector: str | None = None,
        on_image: ImageHandler | None = None,
    ) -> None:
        """Configure the session; nothing connects until `run` is awaited."""
        self.selector = selector
        self.on_image = on_image
        self.client: object | None = None
        self.write_characteristic: object | None = None
        self.control = bytearray()
        self.control_frames: list[tuple[int, bytes]] = []
        self.files = FileReassembler()
        self.file_updates: asyncio.Queue[None] = asyncio.Queue(maxsize=512)
        self._has_file_notify = False
        self._connected = asyncio.Event()
        self._capture_lock = asyncio.Lock()
        # The run loop is the only consumer of `file_updates`. A capture parks a
        # future here instead of reading the queue itself, so the two can never
        # race for the same notification.
        self._pending: asyncio.Future[bytes] | None = None
        self._stop = asyncio.Event()
        self.connected_since: float | None = None
        self.images_received = 0
        self.last_image_at: float | None = None
        self.reconnects = 0

    # ---- notification sinks -------------------------------------------------

    def _on_control(self, _: object, value: bytearray) -> None:
        self.control.extend(value)
        for frame in _decode_control(self.control):
            self.control_frames.append(frame)
            logger.debug("control frame %02X %s", frame[0], frame[1].hex())

    def _on_file(self, _: object, value: bytearray) -> None:
        self.files.push(bytes(value))
        try:
            self.file_updates.put_nowait(None)
        except asyncio.QueueFull:
            logger.warning("file notification queue overflow; resetting reassembler")
            self.files.reset()

    # ---- link lifecycle -----------------------------------------------------

    async def _connect_once(self) -> None:
        if BleakClient is None:
            raise LumaBleError("Bleak is required: install `bleak` in the bridge environment")
        devices = await discover(self.selector)
        device = choose_device(devices, self.selector)
        client = BleakClient(device, timeout=CONNECT_SECONDS, disconnected_callback=self._on_disconnect)
        await asyncio.wait_for(client.connect(), timeout=CONNECT_SECONDS)
        services = client.services
        write = _find_characteristic(services, WRITE)
        control = _find_characteristic(services, CONTROL_NOTIFY)
        file_channel = _find_characteristic(services, FILE_NOTIFY)
        if write is None or control is None:
            await client.disconnect()
            raise LumaBleError("selected device does not expose AA13 and AA14")
        await client.start_notify(control, self._on_control)
        if file_channel is not None:
            await client.start_notify(file_channel, self._on_file)
        self._has_file_notify = file_channel is not None
        self.client = client
        self.write_characteristic = write
        self.connected_since = time.time()
        self._connected.set()
        logger.info(
            "connected to %s (%s), file channel %s",
            getattr(device, "name", "?"),
            getattr(device, "address", "?"),
            "present" if self._has_file_notify else "absent",
        )

    def _on_disconnect(self, _: object) -> None:
        logger.warning("glasses disconnected")
        self._connected.clear()
        self.client = None
        self.connected_since = None

    async def _drain_completed_files(self) -> None:
        """Hand over any finished file and clear the reassembler for the next one."""
        if self.files.error:
            detail = self.files.error
            logger.warning("file stream error: %s", detail)
            self.files.reset()
            if self._pending is not None and not self._pending.done():
                self._pending.set_exception(LumaBleError(detail))
            return
        image = self.files.completed
        if image is None:
            return
        self.files.reset()
        self.images_received += 1
        self.last_image_at = time.time()

        # A waiting capture owns this image; anything else arrived unprompted.
        if self._pending is not None and not self._pending.done():
            logger.info("image received for capture: %d bytes", len(image))
            self._pending.set_result(image)
            return

        logger.info("unsolicited image: %d bytes (total %d)", len(image), self.images_received)
        if self.on_image is not None:
            try:
                await self.on_image(image)
            except Exception:
                logger.exception("on_image handler failed")

    async def run(self) -> None:
        """Hold the link open until `stop` is called, reconnecting as needed."""
        backoff = RECONNECT_MIN_S
        while not self._stop.is_set():
            try:
                await self._connect_once()
                backoff = RECONNECT_MIN_S
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("connect failed (%s); retrying in %.0fs", error, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX_S)
                self.reconnects += 1
                continue

            try:
                while self._connected.is_set() and not self._stop.is_set():
                    try:
                        await asyncio.wait_for(self.file_updates.get(), timeout=IDLE_POLL_S)
                    except asyncio.TimeoutError:
                        pass
                    await self._drain_completed_files()
            finally:
                await self._disconnect()

            if not self._stop.is_set():
                self.reconnects += 1
                await asyncio.sleep(RECONNECT_MIN_S)

    async def _disconnect(self) -> None:
        client = self.client
        self.client = None
        self._connected.clear()
        self.connected_since = None
        if client is not None:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception:
                logger.debug("disconnect raised", exc_info=True)

    async def stop(self) -> None:
        """Ask `run` to exit and close the link."""
        self._stop.set()
        await self._disconnect()

    # ---- commands -----------------------------------------------------------

    async def wait_connected(self, timeout: float = 60.0) -> None:
        """Block until the link is up, or raise once *timeout* passes."""
        await asyncio.wait_for(self._connected.wait(), timeout=timeout)

    async def write(self, opcode: int, payload: bytes = b"") -> None:
        """Send one command frame on the live link."""
        if self.client is None or self.write_characteristic is None:
            raise LumaBleError("not connected")
        await self.client.write_gatt_char(
            self.write_characteristic, command_frame(opcode, payload), response=True
        )

    async def capture(self, timeout: float = PHOTO_SECONDS) -> bytes:
        """Trigger one AI photo and return it, reusing the open link."""
        if not self._has_file_notify:
            raise LumaBleError("selected device has no AA15 file notification characteristic")
        async with self._capture_lock:
            self.files.reset()
            pending: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
            self._pending = pending
            try:
                await self.write(0x22, b"1")
                return await asyncio.wait_for(pending, timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise LumaBleError("timed out waiting for AI image") from exc
            finally:
                self._pending = None


# ---- CLI --------------------------------------------------------------------


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


async def _listen(args: argparse.Namespace) -> int:
    """Hold the link open and save whatever the glasses push, unprompted."""
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    async def save(image: bytes) -> None:
        path = out_dir / f"glasses-{_stamp()}.jpg"
        path.write_bytes(image)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] unsolicited image: "
              f"{len(image)} bytes -> {path}", flush=True)

    session = LumaSession(selector=(os.getenv("LUMA_DEVICE") or "").strip() or None, on_image=save)
    task = asyncio.create_task(session.run())
    try:
        await session.wait_connected(timeout=args.timeout)
        print(f"Connected. Listening {args.seconds:.0f}s - press the shutter on the glasses now.",
              flush=True)
        end = time.time() + args.seconds
        seen_control = 0
        while time.time() < end:
            await asyncio.sleep(1.0)
            if len(session.control_frames) != seen_control:
                for opcode, payload in session.control_frames[seen_control:]:
                    print(f"  control {opcode:02X} {payload.hex()}", flush=True)
                seen_control = len(session.control_frames)
        print(f"Done. images={session.images_received} control_frames={len(session.control_frames)} "
              f"reconnects={session.reconnects}", flush=True)
        return 0
    finally:
        await session.stop()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def _capture(args: argparse.Namespace) -> int:
    """Take N photos over one link to show the per-shot cost without reconnects."""
    session = LumaSession(selector=(os.getenv("LUMA_DEVICE") or "").strip() or None)
    task = asyncio.create_task(session.run())
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        t0 = time.time()
        await session.wait_connected(timeout=args.timeout)
        print(f"link up in {time.time() - t0:.1f}s", flush=True)
        for index in range(args.count):
            start = time.time()
            image = await session.capture()
            path = out_dir / f"glasses-{_stamp()}-{index + 1}.jpg"
            path.write_bytes(image)
            print(f"shot {index + 1}: {len(image)} bytes in {time.time() - start:.1f}s -> {path}",
                  flush=True)
            if index + 1 < args.count:
                await asyncio.sleep(args.interval)
        return 0
    finally:
        await session.stop()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m bridge.luma_daemon`."""
    parser = argparse.ArgumentParser(description="Persistent Luma glasses link")
    parser.add_argument("--out", default=".runtime/glasses", help="directory for received images")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for the link")
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    listen = subparsers.add_parser("listen", help="save images the glasses push on their own")
    listen.add_argument("--seconds", type=float, default=60.0)

    capture = subparsers.add_parser("capture", help="take photos over one persistent link")
    capture.add_argument("--count", type=int, default=3)
    capture.add_argument("--interval", type=float, default=2.0)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    runner = {"listen": _listen, "capture": _capture}[args.command]
    return asyncio.run(runner(args))


if __name__ == "__main__":
    sys.exit(main())

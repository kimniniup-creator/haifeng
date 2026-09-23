"""Minimal Windows BLE fallback for Luma-compatible glasses.

The wire format and command order are derived from the pinned ``luma-core``
snapshot (``edef1eca9a565d4f6b4330f3327c48b0e0869425``), which is MIT licensed
by the luma-core authors.  This module deliberately implements only the
read-only handshake and photo capture path needed by this project.  It has
unit tests for protocol handling, but has not been verified against hardware.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

try:  # Keep imports usable for unit tests and clear at the CLI boundary.
    from bleak import BleakClient, BleakScanner
except ImportError:  # pragma: no cover - exercised only without optional dependency.
    BleakClient = BleakScanner = None  # type: ignore[assignment,misc]


SERVICE = "AA12"
WRITE = "AA13"
CONTROL_NOTIFY = "AA14"
FILE_NOTIFY = "AA15"
SCAN_SECONDS = 8.0
CONNECT_SECONDS = 12.0
HANDSHAKE_SECONDS = 8.0
PHOTO_SECONDS = 13.0
FILE_STALL_SECONDS = 5.0
MAX_FRAME_LENGTH = 4096
MAX_FILE_BYTES = 16 * 1024 * 1024


class LumaBleError(RuntimeError):
    """A predictable failure that callers can expose as a capture failure."""


def _short_uuid(value: object) -> str:
    return str(value).upper().replace("-", "")


def _has_short_uuid(values: Iterable[object], short: str) -> bool:
    return any(short.upper() in _short_uuid(value) for value in values)


def checksum(command: int, payload: bytes) -> int:
    return (command + sum(payload)) & 0xFF


def command_frame(command: int, payload: bytes = b"") -> bytes:
    """Encode one AB55 command; empty read commands carry the observed 00 filler."""
    payload = payload or b"\x00"
    length = 1 + len(payload) + 1
    return b"\xAB\x55" + length.to_bytes(2, "big") + bytes([command]) + payload + bytes([checksum(command, payload)])


def _decode_control(buffer: bytearray) -> list[tuple[int, bytes]]:
    """Drain valid AC55 frames, retaining a possible trailing partial frame."""
    frames: list[tuple[int, bytes]] = []
    while True:
        if len(buffer) < 2:
            return frames
        if buffer[:2] != b"\xAC\x55":
            position = bytes(buffer).find(b"\xAC\x55", 1)
            if position < 0:
                keep = 1 if buffer[-1:] == b"\xAC" else 0
                del buffer[: len(buffer) - keep]
                return frames
            del buffer[:position]
        if len(buffer) < 4:
            return frames
        length = int.from_bytes(buffer[2:4], "big")
        if length < 2 or length > MAX_FRAME_LENGTH:
            del buffer[:2]
            continue
        total = 4 + length
        if len(buffer) < total:
            return frames
        command = buffer[4]
        payload = bytes(buffer[5 : total - 1])
        valid = buffer[total - 1] == checksum(command, payload)
        del buffer[:total]
        if valid:
            frames.append((command, payload))


@dataclass
class _Transfer:
    total: int
    file_type: int
    data: bytearray
    ranges: list[tuple[int, int]] = field(default_factory=list)

    def insert(self, start: int, end: int) -> None:
        merged: list[tuple[int, int]] = []
        placed = False
        for left, right in self.ranges:
            if right < start:
                merged.append((left, right))
            elif end < left:
                if not placed:
                    merged.append((start, end))
                    placed = True
                merged.append((left, right))
            else:
                start, end = min(start, left), max(end, right)
        if not placed:
            merged.append((start, end))
        self.ranges = merged

    @property
    def received(self) -> int:
        return sum(end - start for start, end in self.ranges)


class FileReassembler:
    """Bounded 5258 stream parser with range coverage, ported from luma-core logic."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._transfer: _Transfer | None = None
        self.completed: bytes | None = None
        self.error: str | None = None

    def reset(self) -> None:
        self._buffer.clear()
        self._transfer = None
        self.completed = None
        self.error = None

    def push(self, value: bytes) -> None:
        if self.completed is not None or self.error is not None:
            return
        self._buffer.extend(value)
        while True:
            if len(self._buffer) < 2:
                return
            if self._buffer[:2] != b"RX":
                index = bytes(self._buffer).find(b"RX", 1)
                if index < 0:
                    keep = 1 if self._buffer[-1:] == b"R" else 0
                    del self._buffer[: len(self._buffer) - keep]
                    return
                del self._buffer[:index]
            if len(self._buffer) < 4:
                return
            length = int.from_bytes(self._buffer[2:4], "big")
            if length < 2 or length > MAX_FRAME_LENGTH:
                del self._buffer[:2]
                continue
            total = 4 + length + 2
            if len(self._buffer) < total:
                return
            frame = bytes(self._buffer[:total])
            del self._buffer[:total]
            if frame[-2:] != b"XR":
                continue
            command = frame[4]
            payload = frame[5 : 4 + length - 1]
            if frame[4 + length - 1] != checksum(command, payload):
                continue
            self._on_frame(command, payload)
            if self.completed is not None or self.error is not None:
                return

    def _fail(self, detail: str) -> None:
        self._transfer = None
        self.error = detail

    def _on_frame(self, command: int, payload: bytes) -> None:
        if command == 0x97:
            if len(payload) != 5:
                return self._fail("invalid file info")
            total = int.from_bytes(payload[:4], "big")
            if not 0 < total <= MAX_FILE_BYTES:
                return self._fail("implausible file size")
            self._transfer = _Transfer(total, payload[4], bytearray(total))
            return
        if command == 0x98:
            if self._transfer is None or len(payload) < 4:
                return
            offset = int.from_bytes(payload[:4], "big")
            chunk = payload[4:]
            end = offset + len(chunk)
            if end > self._transfer.total:
                return self._fail("file chunk outside declared range")
            self._transfer.data[offset:end] = chunk
            self._transfer.insert(offset, end)
            return
        if command == 0x99:
            transfer, self._transfer = self._transfer, None
            if transfer is None:
                return self._fail("file ended without file info")
            if transfer.received != transfer.total:
                return self._fail("incomplete file transfer")
            self.completed = bytes(transfer.data)


def _file_frame(command: int, payload: bytes) -> bytes:
    """Public for tests; the device never receives this frame from this CLI."""
    length = 1 + len(payload) + 1
    return b"RX" + length.to_bytes(2, "big") + bytes([command]) + payload + bytes([checksum(command, payload)]) + b"XR"


def _device_name(device: object, advertisement: object | None = None) -> str | None:
    return getattr(advertisement, "local_name", None) or getattr(device, "name", None)


def _advertises_service(device: object, advertisement: object | None = None) -> bool:
    metadata = getattr(device, "metadata", {}) or {}
    uuids = list(getattr(advertisement, "service_uuids", []) or []) + list(metadata.get("uuids", []) or [])
    return _has_short_uuid(uuids, SERVICE)


def _matches_selector(device: object, selector: str) -> bool:
    return selector.casefold() in {str(getattr(device, "address", "")).casefold(), str(getattr(device, "name", "")).casefold()}


def _candidate(device: object, advertisement: object | None = None) -> bool:
    name = (_device_name(device, advertisement) or "").upper()
    return _advertises_service(device, advertisement) or name.startswith(("E06", "E09"))


async def discover(selector: str | None = None, timeout: float = SCAN_SECONDS) -> list[object]:
    if BleakScanner is None:
        raise LumaBleError("Bleak is required: install `bleak` in the bridge environment")
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    values: Sequence[tuple[object, object | None]]
    values = list(devices.values()) if isinstance(devices, dict) else [(device, None) for device in devices]
    matches = [device for device, advertisement in values if _matches_selector(device, selector)] if selector else [device for device, advertisement in values if _candidate(device, advertisement)]
    if selector and not matches:
        raise LumaBleError(f"LUMA_DEVICE {selector!r} was not discovered")
    return matches


def choose_device(devices: Sequence[object], selector: str | None) -> object:
    if not devices:
        raise LumaBleError("no E06/E09 or AA12 Luma device found")
    if selector:
        return devices[0]
    if len(devices) != 1:
        names = ", ".join(f"{getattr(d, 'name', None) or '(unnamed)'} [{getattr(d, 'address', '?')}]" for d in devices)
        raise LumaBleError(f"ambiguous Luma scan; set LUMA_DEVICE to a name or address: {names}")
    return devices[0]


def _find_characteristic(services: object, short: str) -> object | None:
    for service in services:
        for characteristic in getattr(service, "characteristics", []):
            if short in _short_uuid(getattr(characteristic, "uuid", "")):
                return characteristic
    return None


class LumaConnection:
    def __init__(self, device: object) -> None:
        self.device = device
        self.client: object | None = None
        self.write_characteristic: object | None = None
        self.control = bytearray()
        self.control_frames: list[tuple[int, bytes]] = []
        self.files = FileReassembler()
        # Queue individual arrivals instead of a shared Event: clearing an Event between
        # adjacent notifications can otherwise lose the only wake-up for a completed image.
        self.file_updates: asyncio.Queue[None] = asyncio.Queue(maxsize=512)

    async def __aenter__(self) -> "LumaConnection":
        if BleakClient is None:
            raise LumaBleError("Bleak is required: install `bleak` in the bridge environment")
        self.client = BleakClient(self.device, timeout=CONNECT_SECONDS)
        try:
            await asyncio.wait_for(self.client.connect(), timeout=CONNECT_SECONDS)
            services = self.client.services
            write = _find_characteristic(services, WRITE)
            control = _find_characteristic(services, CONTROL_NOTIFY)
            file = _find_characteristic(services, FILE_NOTIFY)
            if write is None or control is None:
                raise LumaBleError("selected device does not expose AA13 and AA14")
            self.write_characteristic = write
            # Subscribe both channels before any command: the device can push capabilities
            # roughly 30 ms after link-up and a photo can begin streaming quickly.
            await self.client.start_notify(control, self._on_control)
            if file is not None:
                await self.client.start_notify(file, self._on_file)
            self._has_file_notify = file is not None
            return self
        except BaseException:
            if self.client.is_connected:
                await self.client.disconnect()
            raise

    async def __aexit__(self, *_: object) -> None:
        if self.client is not None and self.client.is_connected:
            await self.client.disconnect()

    def _on_control(self, _: object, value: bytearray) -> None:
        self.control.extend(value)
        self.control_frames.extend(_decode_control(self.control))

    def _on_file(self, _: object, value: bytearray) -> None:
        self.files.push(bytes(value))
        try:
            self.file_updates.put_nowait(None)
        except asyncio.QueueFull:
            self.files._fail("file notification queue overflow")

    async def write(self, opcode: int, payload: bytes = b"") -> None:
        assert self.client is not None and self.write_characteristic is not None
        await self.client.write_gatt_char(self.write_characteristic, command_frame(opcode, payload), response=True)

    async def info(self) -> list[tuple[int, bytes]]:
        self.control_frames.clear()
        for opcode in (0x55, 0x64, 0x17, 0x45, 0x48, 0x69, 0x95, 0x71):
            await self.write(opcode)
            await asyncio.sleep(0.12)
        await asyncio.sleep(HANDSHAKE_SECONDS)
        return self.control_frames.copy()

    async def photo(self, ai: bool) -> bytes | None:
        if ai and not self._has_file_notify:
            raise LumaBleError("selected device has no AA15 file notification characteristic")
        self.files.reset()
        while not self.file_updates.empty():
            self.file_updates.get_nowait()
        await self.write(0x22, b"1" if ai else b"0")
        if not ai:
            return None
        deadline = asyncio.get_running_loop().time() + PHOTO_SECONDS
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise LumaBleError("timed out waiting for AI image")
            try:
                await asyncio.wait_for(self.file_updates.get(), timeout=min(remaining, FILE_STALL_SECONDS))
            except asyncio.TimeoutError as exc:
                raise LumaBleError("file stream stalled") from exc
            if self.files.error:
                raise LumaBleError(self.files.error)
            if self.files.completed is not None:
                return self.files.completed


async def _run_cli(args: argparse.Namespace) -> int:
    selector = (os.getenv("LUMA_DEVICE") or "").strip() or None
    devices = await discover(selector)
    if args.command == "scan":
        for device in devices:
            print(f"{getattr(device, 'address', '?')}  {getattr(device, 'name', None) or '(unnamed)'}")
        return 0
    device = choose_device(devices, selector)
    async with LumaConnection(device) as glasses:
        if args.command == "info":
            for opcode, payload in await glasses.info():
                print(f"{opcode:02X} {payload.hex()}")
            return 0
        image = await glasses.photo(args.ai)
        if args.ai:
            assert image is not None
            Path(args.output).write_bytes(image)
            print(f"{len(image)} bytes -> {args.output}")
        else:
            print("photo requested; retrieve the full-resolution file through the Wi-Fi gallery path")
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Luma BLE fallback (not hardware verified)")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("scan")
    subparsers.add_parser("info")
    photo = subparsers.add_parser("photo")
    photo.add_argument("--ai", action="store_true", help="receive the BLE AI JPEG")
    photo.add_argument("output", nargs="?", default="ai.jpg")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run_cli(args))
    except (LumaBleError, asyncio.TimeoutError, OSError) as exc:
        print(f"luma BLE error: {exc}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

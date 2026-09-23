import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile


class LumaUnavailable(RuntimeError):
    pass


class LumaAdapter:
    def __init__(self, mode: str, cli_path: str, timeout_seconds: float = 40):
        self.mode = mode
        self.cli_path = cli_path
        self.timeout_seconds = timeout_seconds
        self.lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None

    @property
    def configured(self) -> bool:
        if self.mode == "python":
            return importlib.util.find_spec("bleak") is not None
        return self.mode == "cli" and bool(self.cli_path) and Path(self.cli_path).exists()

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def cancel(self) -> None:
        if self._process:
            await self._terminate(self._process)

    async def capture(self) -> bytes:
        if not self.configured:
            raise LumaUnavailable("LUMA_NOT_CONFIGURED")
        async with self.lock:
            with tempfile.TemporaryDirectory(prefix="luma-capture-") as directory:
                output = Path(directory) / "capture.jpg"
                command = ([sys.executable, "-m", "bridge.luma_ble"] if self.mode == "python" else [self.cli_path])
                process = await asyncio.create_subprocess_exec(
                    *command, "photo", "--ai", str(output),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                self._process = process
                try:
                    _, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
                except asyncio.CancelledError:
                    await self._terminate(process)
                    raise
                except asyncio.TimeoutError as exc:
                    await self._terminate(process)
                    raise LumaUnavailable("LUMA_CAPTURE_TIMEOUT") from exc
                finally:
                    if self._process is process:
                        self._process = None
                if process.returncode != 0 or not output.exists():
                    detail = stderr.decode(errors="replace")[-300:]
                    raise LumaUnavailable(f"LUMA_CAPTURE_FAILED:{detail}")
                return output.read_bytes()

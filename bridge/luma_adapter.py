import asyncio
from pathlib import Path
import tempfile


class LumaUnavailable(RuntimeError):
    pass


class LumaAdapter:
    def __init__(self, mode: str, cli_path: str):
        self.mode = mode
        self.cli_path = cli_path
        self.lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return self.mode == "cli" and bool(self.cli_path) and Path(self.cli_path).exists()

    async def capture(self) -> bytes:
        if not self.configured:
            raise LumaUnavailable("LUMA_NOT_CONFIGURED")
        async with self.lock:
            with tempfile.TemporaryDirectory(prefix="luma-capture-") as directory:
                output = Path(directory) / "capture.jpg"
                process = await asyncio.create_subprocess_exec(
                    self.cli_path, "photo", "--ai", str(output),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
                if process.returncode != 0 or not output.exists():
                    detail = stderr.decode(errors="replace")[-300:]
                    raise LumaUnavailable(f"LUMA_CAPTURE_FAILED:{detail}")
                return output.read_bytes()

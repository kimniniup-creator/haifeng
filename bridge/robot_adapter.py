import httpx


class RobotAdapter:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def status(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                response = await client.get(f"{self.base_url}/api/daemon/status")
                response.raise_for_status()
            return {"connected": True, "details": response.json()}
        except Exception as exc:
            return {"connected": False, "error_code": "ROBOT_UNAVAILABLE", "detail": str(exc)}

    async def acknowledge(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.post(
                    f"{self.base_url}/api/move/goto",
                    json={"antennas": [0.15, -0.15], "duration": 1.0},
                )
                response.raise_for_status()
            return {"motion_status": "started", "audio_status": "not_configured"}
        except Exception as exc:
            return {"motion_status": "failed", "audio_status": "not_configured", "error_code": "ROBOT_MOTION_FAILED", "detail": str(exc)}

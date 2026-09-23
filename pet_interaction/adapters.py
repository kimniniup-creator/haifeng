"""Owner adapters only; no daemon, microphone, camera or SDK ownership here."""


class FakeMotion:
    def __init__(self):
        self.calls = []
        self.turn = None
        self.cancel_count = 0

    async def set_turn(self, turn_id):
        self.turn = turn_id

    async def submit(self, semantic, turn_id, ttl_seconds, request_id=None, *, start_deadline=None, execution_budget_seconds=None):
        if ttl_seconds <= 0 or turn_id != self.turn:
            return {"status": "rejected", "reason": "expired_or_stale"}
        self.calls.append({"semantic": semantic, "turn_id": turn_id, "request_id": request_id,
                           "start_deadline": start_deadline, "execution_budget_seconds": execution_budget_seconds})
        return {"status": "dry_run", "reason": "devices_disabled", "request_id": request_id}

    async def cancel(self):
        self.cancel_count += 1

    async def invalidate_baseline(self):
        await self.cancel()

    async def close(self):
        await self.cancel()


class FakeVoice:
    def __init__(self):
        self.calls = []
        self.interrupt_count = 0

    async def respond(self, payload):
        self.calls.append(dict(payload))
        return {"status": "dry_run", "reason": "devices_disabled"}

    async def interrupt(self):
        self.interrupt_count += 1
        return {"status": "dry_run"}

    async def close(self):
        pass


class HttpVoice:
    """Constructed only for explicit device mode; exact endpoints owned by voice."""
    def __init__(self, base_url, client=None):
        import httpx
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.username or parsed.password:
            raise ValueError("voice_endpoint_must_be_loopback_http")
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(base_url=self.base_url, timeout=2, trust_env=False)

    async def respond(self, payload):
        # Never retries: a lost response is not permission to replay sound.
        response = await self.client.post("/api/agent-result", json=payload)
        if response.status_code >= 400:
            return {"status": "rejected", "reason": f"voice_http_{response.status_code}"}
        result = response.json()
        return {"status": "queued" if result.get("accepted") is True else "rejected", "receipt": result}

    async def interrupt(self):
        response = await self.client.post("/api/interrupt", json={})
        response.raise_for_status()
        return {"status": "interrupted"}

    async def close(self):
        await self.client.aclose()


def as_result(result):
    if isinstance(result, dict):
        return result
    from dataclasses import asdict, is_dataclass
    if is_dataclass(result):
        return asdict(result)
    return {"status": "failed", "reason": "invalid_adapter_result"}

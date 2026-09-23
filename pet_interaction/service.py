"""Loopback JSON API. Import safe: construction and startup are explicit."""
import asyncio
import json
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from .controller import PetController


def create_app(controller=None, tokens=None, voice_url=None):
    controller = controller or PetController()
    tokens = tokens or {}
    if not tokens or any(not isinstance(v, str) or len(v) < 24 for v in tokens.values()):
        raise ValueError("provide_role_tokens_of_at_least_24_characters")
    if len(set(tokens.values())) != len(tokens):
        raise ValueError("role_tokens_must_be_distinct")
    if not set(tokens) <= {"operator", "vision"}:
        raise ValueError("invalid_role")

    @asynccontextmanager
    async def lifespan(app):
        from .voice_link import run_voice_link
        shutdown = asyncio.Event()
        async def expiry_loop():
            while not shutdown.is_set():
                await controller.tick()
                await asyncio.sleep(0.2)
        expiry = asyncio.create_task(expiry_loop())
        link = asyncio.create_task(run_voice_link(controller, voice_url, shutdown)) if voice_url else None
        proactive_link = asyncio.create_task(controller.proactive.run(controller, shutdown)) if controller.proactive else None
        if proactive_link:
            def proactive_done(task):
                if not task.cancelled():
                    error = task.exception()
                    controller.proactive_link_error = type(error).__name__ if error else None
            proactive_link.add_done_callback(proactive_done)
        if link:
            def link_done(task):
                if not task.cancelled():
                    error = task.exception()
                    controller.voice_link_error = type(error).__name__ if error else None
            link.add_done_callback(link_done)
        app.state.voice_link = link
        try:
            yield
        finally:
            shutdown.set()
            expiry.cancel()
            await asyncio.gather(expiry, return_exceptions=True)
            if link:
                link.cancel()
                await asyncio.gather(link, return_exceptions=True)
            if proactive_link:
                proactive_link.cancel()
                await asyncio.gather(proactive_link, return_exceptions=True)
            await controller.close()

    app = FastAPI(title="啾啾交互后端", lifespan=lifespan)
    app.state.controller = controller

    def role(request):
        # CLI producers do not send Origin. Browser mutations are not an implicit authority.
        if request.headers.get("origin"):
            raise HTTPException(403, "browser_origin_not_allowed")
        supplied = request.headers.get("authorization", "")
        for name, token in tokens.items():
            if secrets.compare_digest(supplied, "Bearer " + token):
                return name
        raise HTTPException(401, "unauthorized")

    @app.get("/health")
    async def health():
        return {"service": "pet-interaction", "status": "ok", "schema_version": 1}

    @app.get("/v1/state")
    async def state(request: Request):
        role(request)
        return controller.snapshot()

    @app.get("/v1/decisions/{decision_id}")
    async def decision(decision_id: str, request: Request):
        role(request)
        result = controller.decisions.get(decision_id)
        if result is None:
            raise HTTPException(404, "unknown_decision")
        return result

    @app.post("/v1/events")
    async def events(request: Request):
        source = role(request)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16384:
                raise HTTPException(413, "event_too_large")
        try:
            def strict_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate_key")
                    result[key] = value
                return result
            value = json.loads(body.decode("utf-8"), object_pairs_hook=strict_object,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non_finite")))
        except (UnicodeError, ValueError):
            raise HTTPException(422, "invalid_json")
        if not isinstance(value, dict) or value.get("source") != source:
            raise HTTPException(403, "source_not_authorized")
        return await controller.handle(value)

    @app.post("/v1/stop")
    async def stop(request: Request):
        if role(request) != "operator":
            raise HTTPException(403, "operator_required")
        import uuid
        return await controller.handle({"schema_version": 1, "source": "operator", "session_id": "operator",
            "event_id": uuid.uuid4().hex, "kind": "stop", "observed_at": controller.clock(),
            "ttl_seconds": 5, "confidence": 1, "payload": {}})

    @app.post("/v1/shutdown")
    async def shutdown(request: Request):
        if role(request) != "operator":
            raise HTTPException(403, "operator_required")
        stop_server = getattr(app.state, "stop_server", None)
        if stop_server is None:
            raise HTTPException(409, "not_managed_by_cli")
        stop_server()
        return {"status": "shutdown_requested", "scope": "this_pet_service_only"}

    return app

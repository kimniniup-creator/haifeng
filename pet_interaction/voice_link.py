"""Normalize the voice owner's event stream without creating a voice epoch."""
import asyncio
import time


async def consume_voice(controller, message):
    kind = message.get("type")
    if kind in {"state", "turn_changed", "speech_started"}:
        body = message.get("state", message) if isinstance(message.get("state"), dict) else message
        return await controller.voice_turn(body["session_id"], body["epoch"], body["turn_id"],
            reason="snapshot" if kind == "state" else ("speech_started" if kind == "speech_started" else body.get("reason", "turn_changed")),
            input_id=body.get("input_id") or None)
    if kind == "turn_input":
        if message.get("phase", "final") != "final":
            return {"status": "suppressed", "reason": "partial"}
        observed = message["observed_at"]
        text = message["text"]
        # ASR homophones are matching aliases only; retain the exact transcript.
        name_called = any(text.strip().startswith(name) for name in ("啾啾", "揪揪", "舅舅"))
        return await controller.handle({"schema_version": 1, "source": "voice", "session_id": message["session_id"],
            "epoch": message["epoch"], "turn_id": message["turn_id"], "input_id": message["input_id"],
            "event_id": message["input_id"], "kind": "wake_word" if name_called else "speech_final",
            "observed_at": observed, "ttl_seconds": min(2.5, message.get("ttl_seconds", 2.5)),
            "confidence": message.get("confidence", 1.0), "payload": {"text": text}})
    if kind == "output_status":
        response_id = message.get("response_id")
        decision = controller.decisions.get(response_id)
        if decision:
            # Diagnostic receipt only. Never resurrect behaviour on a late completion.
            decision["voice_receipt"] = {k: message[k] for k in ("status", "reason") if k in message}
        return {"status": "observed"}
    return {"status": "ignored"}


async def run_voice_link(controller, base_url, shutdown):
    """Explicit subscription transfers automatic-ack ownership. No auto reconnect/replay."""
    import json
    from websockets.asyncio.client import connect
    url = base_url.replace("http://", "ws://", 1).rstrip("/") + "/events"
    try:
        async with connect(url, open_timeout=3, max_size=65536, proxy=None) as socket:
            await socket.send(json.dumps({"type": "subscribe", "consumer": "pet-agent"}))
            while not shutdown.is_set():
                try:
                    message = await asyncio.wait_for(socket.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                await consume_voice(controller, json.loads(message))
    finally:
        await controller.disconnect_voice()

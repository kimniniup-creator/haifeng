import asyncio
import json
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx

from pet_motion import MotionExecutor
from pet_motion.transport import DaemonError, _Session


class FakeDaemon:
    def __init__(self):
        self.starts = []
        self.stops = []
        self.events = asyncio.Queue()
        self.started = asyncio.Event()
        self.release_start = asyncio.Event()
        self.release_start.set()
        self.error = None
        self.stop_error = False
        self.sessions = 0
        self.max_sessions = 0

    @asynccontextmanager
    async def session(self):
        self.sessions += 1
        self.max_sessions = max(self.max_sessions, self.sessions)
        try:
            yield self
        finally:
            self.sessions -= 1

    async def start(self, mapping):
        uuid = str(uuid4())
        self.starts.append((uuid, mapping["action_id"]))
        self.started.set()
        await self.release_start.wait()
        if self.error:
            raise self.error
        return uuid

    async def wait(self, uuid):
        while True:
            event = await self.events.get()
            if isinstance(event, Exception):
                raise event
            if event[0] == uuid:
                return event[1]

    async def stop(self, uuid):
        self.stops.append(uuid)
        if self.stop_error:
            raise ConnectionError("disconnected")
        await self.events.put((uuid, "move_cancelled"))


class MotionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.daemon = FakeDaemon()
        self.executor = MotionExecutor(self.daemon, dry_run=False, stop_timeout=.05)
        # Keep the recorded transport cases independent of the default semantic
        # choice; micro motion has its own measured-device fixture.
        self.executor.mappings["attention"] = {"dataset": "pollen-robotics/reachy-mini-emotions-library", "action_id": "attentive1", "approved": True}
        # Test-only approval: production defaults remain unapproved.
        for mapping in self.executor.mappings.values():
            mapping["approved"] = True
        await self.executor.set_turn("voice:a:1")

    async def asyncTearDown(self):
        await self.executor.close()

    async def submit(self, **kwargs):
        return await self.executor.submit("attention", "voice:a:1", kwargs.pop("ttl_seconds", 10), **kwargs)

    async def running(self):
        result = await self.submit()
        await self.daemon.started.wait()
        return result

    async def test_default_dry_run_never_opens_transport(self):
        executor = MotionExecutor(self.daemon)
        await executor.set_turn("t")
        result = await executor.submit("attention", "t", 3)
        self.assertEqual(result.status, "dry_run")
        self.assertEqual(self.daemon.starts, [])
        await executor.close()

    async def test_live_unapproved_rejected(self):
        self.executor.mappings["attention"]["approved"] = False
        self.assertEqual((await self.submit()).reason, "mapping_not_approved")
        self.assertFalse(self.daemon.starts)

    async def test_200_is_running_until_matching_terminal(self):
        result = await self.running()
        await self.daemon.events.put(("unrelated", "move_completed"))
        waiter = asyncio.create_task(self.executor.wait(result.request_id))
        await asyncio.sleep(.01)
        self.assertFalse(waiter.done())
        await self.daemon.events.put((self.daemon.starts[0][0], "move_completed"))
        self.assertEqual((await waiter).status, "completed")

    async def test_serial_and_queue_bound(self):
        self.executor.capacity = 1
        first = await self.running()
        second = await self.submit()
        third = await self.submit()
        self.assertEqual(second.status, "queued")
        self.assertEqual(third.reason, "queue_full")
        self.assertEqual(len(self.daemon.starts), 1)
        await self.daemon.events.put((self.daemon.starts[0][0], "move_completed"))
        await self.executor.wait(first.request_id)
        await self.executor.cancel()
        self.assertLessEqual(self.daemon.max_sessions, 1)

    async def test_old_turn_rejected_and_same_turn_preserves_active(self):
        result = await self.running()
        await self.executor.set_turn("voice:a:1")
        self.assertEqual(self.daemon.stops, [])
        await self.executor.set_turn("voice:a:2")
        self.assertEqual((await self.executor.wait(result.request_id)).status, "cancelled")
        self.assertEqual((await self.submit()).reason, "stale_turn")
        self.assertEqual(self.daemon.stops, [self.daemon.starts[0][0]])

    async def test_queue_ttl_expires_without_playback(self):
        first = await self.running()
        second = await self.submit(ttl_seconds=.01)
        await asyncio.sleep(.02)
        await self.daemon.events.put((self.daemon.starts[0][0], "move_completed"))
        await self.executor.wait(first.request_id)
        self.assertEqual((await self.executor.wait(second.request_id)).status, "expired")
        self.assertEqual(len(self.daemon.starts), 1)

    async def test_active_ttl_stops_uuid(self):
        result = await self.submit(ttl_seconds=.3)
        await self.daemon.started.wait()
        final = await self.executor.wait(result.request_id)
        self.assertEqual(final.status, "expired")
        self.assertEqual(self.daemon.stops, [final.uuid])

    async def test_stop_clears_pending_even_when_queue_full(self):
        first = await self.running()
        pending = [await self.submit() for _ in range(4)]
        stop = await self.executor.submit("stop", "old", 0)
        self.assertEqual(stop.status, "stopped")
        self.assertEqual((await self.executor.wait(first.request_id)).status, "cancelled")
        for receipt in pending:
            self.assertEqual((await self.executor.wait(receipt.request_id)).status, "cancelled")
        self.assertEqual(len(self.daemon.starts), 1)

    async def test_cancel_during_post_recovers_uuid_then_stops(self):
        self.daemon.release_start.clear()
        result = await self.running()
        stop = asyncio.create_task(self.executor.cancel())
        await asyncio.sleep(.01)
        self.assertFalse(stop.done())
        self.daemon.release_start.set()
        await stop
        final = await self.executor.wait(result.request_id)
        self.assertEqual(self.daemon.stops, [final.uuid])
        self.assertEqual(final.status, "cancelled")

    async def test_disconnect_drops_queue_and_never_replays(self):
        first = await self.running()
        second = await self.submit()
        await self.daemon.events.put(ConnectionError("lost"))
        self.assertEqual((await self.executor.wait(first.request_id)).status, "failed")
        self.assertEqual((await self.executor.wait(second.request_id)).status, "cancelled")
        self.assertFalse(self.executor.available)
        await self.executor.set_turn("voice:new:0")
        self.assertEqual((await self.executor.submit("attention", "voice:new:0", 10)).status, "rejected")
        self.assertEqual(len(self.daemon.starts), 1)

    async def test_stop_failure_faults_and_blocks_next(self):
        result = await self.running()
        self.daemon.stop_error = True
        await self.executor.cancel()
        self.assertEqual((await self.executor.wait(result.request_id)).reason, "stop_unconfirmed")
        self.assertFalse(self.executor.available)

    async def test_failed_event_is_not_success_and_discards_queue(self):
        first = await self.running()
        second = await self.submit()
        await self.daemon.events.put((self.daemon.starts[0][0], "move_failed"))
        self.assertEqual((await self.executor.wait(first.request_id)).status, "failed")
        self.assertEqual((await self.executor.wait(second.request_id)).status, "cancelled")
        self.assertFalse(self.executor.available)

    async def test_stop_http_ack_without_terminal_event_latches_fault(self):
        async def acknowledge_only(uuid):
            self.daemon.stops.append(uuid)
        self.daemon.stop = acknowledge_only
        first = await self.running()
        await self.executor.cancel()
        self.assertEqual((await self.executor.wait(first.request_id)).status, "failed")
        self.assertEqual(self.executor.fault, "stop_unconfirmed")

    async def test_cancelling_stop_caller_still_finishes_handshake(self):
        self.daemon.release_start.clear()
        first = await self.running()
        stop = asyncio.create_task(self.executor.cancel())
        await asyncio.sleep(.01)
        stop.cancel()
        await asyncio.sleep(.01)
        self.assertFalse(stop.done())
        self.assertFalse(self.executor.available)
        self.daemon.release_start.set()
        await asyncio.gather(stop, return_exceptions=True)
        final = await self.executor.wait(first.request_id)
        self.assertEqual(final.status, "cancelled")
        self.assertEqual(self.daemon.stops, [final.uuid])

    async def test_failed_event_during_stop_is_fault(self):
        async def fail_stop(uuid):
            await self.daemon.events.put((uuid, "move_failed"))
        self.daemon.stop = fail_stop
        first = await self.running()
        await self.executor.cancel()
        self.assertEqual((await self.executor.wait(first.request_id)).status, "failed")
        self.assertEqual(self.executor.fault, "move_failed_during_stop")

    async def test_stop_error_with_buffered_completion_does_not_fault(self):
        async def already_completed(uuid):
            await self.daemon.events.put((uuid, "move_completed"))
            raise RuntimeError("daemon removed UUID before stop arrived")
        self.daemon.stop = already_completed
        first = await self.running()
        await self.executor.cancel()
        final = await self.executor.wait(first.request_id)
        self.assertEqual(final.status, "cancelled")
        self.assertTrue(self.executor.available)
        self.assertEqual(self.executor.fault, "")

    async def test_cancelled_waiter_does_not_cancel_physical_request(self):
        first = await self.running()
        waiter = asyncio.create_task(self.executor.wait(first.request_id))
        await asyncio.sleep(0)
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        await self.daemon.events.put((self.daemon.starts[0][0], "move_completed"))
        self.assertEqual((await self.executor.wait(first.request_id)).status, "completed")

    async def test_busy_rejected_no_retry(self):
        self.daemon.error = DaemonError("daemon_busy")
        result = await self.submit()
        self.assertEqual((await self.executor.wait(result.request_id)).reason, "daemon_busy")
        self.assertEqual(len(self.daemon.starts), 1)

    async def test_ambiguous_start_faults_without_retry(self):
        self.daemon.error = DaemonError("start_outcome_unknown", uncertain=True)
        result = await self.submit()
        self.assertEqual((await self.executor.wait(result.request_id)).status, "failed")
        self.assertFalse(self.executor.available)
        self.assertEqual((await self.submit()).status, "rejected")

    async def test_duplicate_request_does_not_repeat(self):
        first = await self.submit(request_id="one")
        second = await self.submit(request_id="one")
        self.assertEqual(first.request_id, second.request_id)
        await self.daemon.started.wait()
        await self.executor.cancel()
        await self.submit(request_id="one")
        self.assertEqual(len(self.daemon.starts), 1)

    async def test_rest_and_quiet_do_not_sleep_robot(self):
        for semantic in ("rest", "quiet"):
            result = await self.executor.submit(semantic, "voice:a:1", 2)
            self.assertEqual(result.status, "noop")
        self.assertFalse(self.daemon.starts)

    async def test_invalid_expiry_unknown_and_close(self):
        for ttl in (0, -1, float("nan"), float("inf")):
            self.assertEqual((await self.submit(ttl_seconds=ttl)).reason, "expired")
        self.assertEqual((await self.executor.submit("bad", "voice:a:1", 1)).reason, "unknown_semantic")
        await self.executor.close()
        self.assertEqual((await self.submit()).reason, "closed")

    async def test_catalog_contains_all_candidates_as_listed(self):
        catalog = json.loads((Path(__file__).parents[1] / "docs/reachy-mapping/actions.json").read_text(encoding="utf-8"))
        available = {a["key"] for a in catalog["actions"] if a["listed"]}
        for mapping in self.executor.mappings.values():
            if mapping.get("action_id"):
                self.assertIn(mapping["dataset"] + "/" + mapping["action_id"], available)


class Socket:
    def __init__(self, events):
        self.events = iter(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return json.dumps(next(self.events))
        except StopIteration:
            raise StopAsyncIteration


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_wire_path_uuid_stop_and_event_filter(self):
        uuid = str(uuid4())
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(200, json={"uuid": uuid})

        socket = Socket([{"uuid": "other", "type": "move_completed"},
                         {"uuid": uuid, "type": "move_started"},
                         {"uuid": uuid, "type": "move_completed"}])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            session = _Session("http://fake", client, socket)
            self.assertEqual(await session.start({"dataset": "Anne-Charlotte/music", "action_id": "paint-it-black"}), uuid)
            self.assertEqual(await session.wait(uuid), "move_completed")
            await session.stop(uuid)
        self.assertEqual(str(requests[0].url), "http://fake/api/move/play/recorded-move-dataset/Anne-Charlotte/music/paint-it-black")
        self.assertEqual(json.loads(requests[1].content), {"uuid": uuid})

    async def test_http_errors_and_invalid_receipt(self):
        for code, body, uncertain in [(409, {}, False), (404, {}, False), (500, {}, True), (200, {}, True)]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(code, json=body))) as client:
                session = _Session("http://fake", client, Socket([]))
                with self.assertRaises(DaemonError) as error:
                    await session.start({"dataset": "a/b", "action_id": "c"})
                self.assertEqual(error.exception.uncertain, uncertain)

    async def test_event_stream_end_is_not_completion(self):
        session = _Session("http://fake", None, Socket([]))
        with self.assertRaises(DaemonError):
            await session.wait("id")

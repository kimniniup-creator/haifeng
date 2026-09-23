import asyncio
import copy
import math
import time
import unittest
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import numpy as np

from pet_motion import MotionExecutor
from pet_motion.micro import checked_pose, target_pose, rotation_distance, validate_profile
from pet_motion.transport import _Session


class MicroDaemon:
    def __init__(self):
        angle = .17
        h = np.array([[math.cos(angle), -math.sin(angle), 0, .007],
                      [math.sin(angle), math.cos(angle), 0, -.002],
                      [0, 0, 1, .003], [0, 0, 0, 1]])
        self.state = {"head_pose": {"m": h.reshape(-1).tolist()},
                      "antennas_position": [.23, -.14], "body_yaw": .08,
                      "control_mode": "enabled"}
        self.origin = copy.deepcopy(self.state)
        self.starts, self.stops, self.holds = [], [], []
        self.events = asyncio.Queue()
        self.started = asyncio.Event()
        self.auto_complete = True
        self.skip_motion = False
        self.active_uuid = None
        self.max_active = 0

    @asynccontextmanager
    async def session(self):
        yield self

    async def snapshot(self):
        if self.active_uuid:
            raise RuntimeError("move still active")
        return copy.deepcopy(self.state)

    async def start(self, mapping):
        assert not self.active_uuid, "concurrent goto"
        assert "_goto" in mapping, "micro must not use recorded motion"
        uuid = str(uuid4())
        self.active_uuid = uuid
        self.starts.append((uuid, copy.deepcopy(mapping["_goto"])))
        self.started.set()
        if self.auto_complete:
            if not self.skip_motion:
                payload = mapping["_goto"]
                self.state.update(head_pose=payload["head_pose"], antennas_position=payload["antennas"], body_yaw=payload["body_yaw"])
            await self.events.put((uuid, "move_completed"))
        return uuid

    async def wait(self, uuid):
        while True:
            event = await self.events.get()
            if event[0] == uuid:
                self.active_uuid = None
                return event[1]

    async def stop(self, uuid):
        self.stops.append(uuid)
        await self.events.put((uuid, "move_cancelled"))

    async def hold_current(self):
        assert not self.active_uuid
        self.holds.append(copy.deepcopy(self.state))


class MicroTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.daemon = MicroDaemon()
        self.motion = MotionExecutor(self.daemon, dry_run=False, stop_timeout=.2)
        self.motion.mappings["attention"]["approved"] = True
        self.motion.micro_profiles["head_micro_nod"]["approved"] = True
        await self.motion.set_turn("probe")

    async def asyncTearDown(self):
        await self.motion.close()

    async def test_measured_relative_nod_then_exact_origin_serially(self):
        receipt = await self.motion.submit("attention", "probe", 10)
        result = await self.motion.wait(receipt.request_id)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.reason, "micro_return_measured")
        self.assertEqual(len(self.daemon.starts), 2)
        origin = checked_pose(self.daemon.origin)
        first, final = (row[1] for row in self.daemon.starts)
        h = np.array(first["head_pose"]["m"]).reshape(4, 4)
        self.assertAlmostEqual(math.degrees(rotation_distance(origin["head"], h)), 1.5, places=6)
        np.testing.assert_allclose(h[:3, 3], origin["head"][:3, 3])
        self.assertEqual(first["antennas"], [.23, -.14])
        self.assertEqual(first["body_yaw"], .08)
        np.testing.assert_allclose(final["head_pose"]["m"], origin["head"].reshape(-1), atol=1e-12)
        self.assertEqual(self.daemon.holds, [])

    async def test_cancel_stops_only_current_uuid_holds_and_never_returns(self):
        self.daemon.auto_complete = False
        receipt = await self.motion.submit("attention", "probe", 10)
        await self.daemon.started.wait()
        await self.motion.cancel()
        result = await self.motion.wait(receipt.request_id)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(self.daemon.stops, [self.daemon.starts[0][0]])
        self.assertEqual(len(self.daemon.starts), 1)
        self.assertEqual(self.daemon.holds, [self.daemon.state])

    async def test_skipped_goto_completion_is_not_success(self):
        self.daemon.skip_motion = True
        self.motion.micro_profiles["head_micro_nod"]["settle_seconds"] = .2
        receipt = await self.motion.submit("attention", "probe", 10)
        result = await self.motion.wait(receipt.request_id)
        self.assertEqual(result.status, "failed")
        self.assertFalse(self.motion.available)
        self.assertEqual(len(self.daemon.starts), 1)
        self.assertEqual(len(self.daemon.holds), 1)

    async def test_too_short_ttl_never_sends_outbound(self):
        receipt = await self.motion.submit("attention", "probe", 2)
        self.assertEqual((await self.motion.wait(receipt.request_id)).reason, "micro_ttl_too_short")
        self.assertEqual(self.daemon.starts, [])

    async def test_fresh_start_can_finish_return_after_event_expires(self):
        self.daemon.auto_complete = False
        receipt = await self.motion.submit("attention", "probe", .5,
                                            start_deadline=time.time()+.5,
                                            execution_budget_seconds=10)
        await self.daemon.started.wait()
        await asyncio.sleep(.6)
        first_uuid, first = self.daemon.starts[0]
        self.daemon.state.update(head_pose=first["head_pose"], antennas_position=first["antennas"], body_yaw=first["body_yaw"])
        self.daemon.auto_complete = True
        await self.daemon.events.put((first_uuid, "move_completed"))
        self.assertEqual((await self.motion.wait(receipt.request_id)).status, "completed")
        self.assertEqual(len(self.daemon.starts), 2)

    async def test_preflight_crossing_original_deadline_never_starts(self):
        original_snapshot = self.daemon.snapshot
        async def slow_snapshot():
            await asyncio.sleep(.05)
            return await original_snapshot()
        self.daemon.snapshot = slow_snapshot
        receipt = await self.motion.submit("attention", "probe", .02,
                                            start_deadline=time.time()+.02,
                                            execution_budget_seconds=10)
        self.assertEqual((await self.motion.wait(receipt.request_id)).status, "expired")
        self.assertEqual(self.daemon.starts, [])

    async def test_new_turn_cancels_independent_budget_in_flight(self):
        self.daemon.auto_complete = False
        receipt = await self.motion.submit("attention", "probe", 2.5,
                                            start_deadline=time.time()+2.5,
                                            execution_budget_seconds=10)
        await self.daemon.started.wait()
        await self.motion.set_turn("new_epoch")
        self.assertEqual((await self.motion.wait(receipt.request_id)).status, "cancelled")
        self.assertEqual(len(self.daemon.starts), 1)
        self.assertEqual(self.daemon.stops, [self.daemon.starts[0][0]])

    async def test_cancel_between_legs_holds_without_return(self):
        verifying = asyncio.Event()
        original_snapshot = self.daemon.snapshot

        async def snapshot():
            if len(self.daemon.starts) == 1 and not self.daemon.active_uuid and not self.daemon.holds:
                verifying.set()
                await asyncio.Event().wait()
            return await original_snapshot()
        self.daemon.snapshot = snapshot
        receipt = await self.motion.submit("attention", "probe", 10)
        await verifying.wait()
        await self.motion.cancel()
        self.assertEqual((await self.motion.wait(receipt.request_id)).status, "cancelled")
        self.assertEqual(len(self.daemon.starts), 1)
        self.assertEqual(len(self.daemon.holds), 1)

    async def test_failed_return_measurement_never_reports_completed(self):
        original_start = self.daemon.start

        async def start(mapping):
            if self.daemon.starts:
                self.daemon.skip_motion = True
            return await original_start(mapping)
        self.daemon.start = start
        self.motion.micro_profiles["head_micro_nod"]["settle_seconds"] = .2
        receipt = await self.motion.submit("attention", "probe", 10)
        self.assertEqual((await self.motion.wait(receipt.request_id)).status, "failed")
        self.assertEqual(len(self.daemon.starts), 2)
        self.assertEqual(len(self.daemon.holds), 1)

    async def test_hold_failure_prevents_next_motion(self):
        async def failed_hold():
            raise RuntimeError("hold ignored")
        self.daemon.hold_current = failed_hold
        self.daemon.auto_complete = False
        receipt = await self.motion.submit("attention", "probe", 10)
        await self.daemon.started.wait()
        await self.motion.cancel()
        self.assertEqual((await self.motion.wait(receipt.request_id)).status, "failed")
        self.assertFalse(self.motion.available)

    async def test_profile_is_separately_gated(self):
        self.motion.micro_profiles["head_micro_nod"]["approved"] = False
        receipt = await self.motion.submit("attention", "probe", 10)
        self.assertEqual(receipt.reason, "micro_profile_not_approved")
        self.assertEqual(self.daemon.starts, [])

    async def test_invalid_pose_never_sends_motion(self):
        self.daemon.state["head_pose"]["m"][0] = float("nan")
        receipt = await self.motion.submit("attention", "probe", 10)
        self.assertEqual((await self.motion.wait(receipt.request_id)).status, "failed")
        self.assertEqual(self.daemon.starts, [])

    async def test_profiles_cannot_raise_hard_limits(self):
        profile = self.motion.micro_profiles["head_micro_nod"]
        for change in ({"delta_degrees": 3}, {"leg_seconds": .1},
                       {"peak_speed_degrees_per_second": 4}, {"delta_degrees": float("nan")},
                       {"axis": "world_y"}):
            with self.assertRaises(ValueError):
                validate_profile({**profile, **change})
        origin = checked_pose(self.daemon.origin)
        target = target_pose(origin, profile)
        self.assertAlmostEqual(math.degrees(rotation_distance(origin["head"], target["head"])), 1.5)

    async def test_native_near_rotation_is_projected_with_translation_preserved(self):
        state = copy.deepcopy(self.daemon.state)
        raw = np.array([[.9972165811070992, .04758257970107439, .06161645446330995],
                        [-.015496377863429913, .896532907062364, -.44273017724239216],
                        [-.07631490460429967, .4403034295052053, .8948742511107254]])
        head = np.array(state["head_pose"]["m"]).reshape(4, 4)
        head[:3, :3] = raw
        state["head_pose"]["m"] = head.reshape(-1).tolist()
        checked = checked_pose(state)
        np.testing.assert_allclose(checked["head"][:3, :3].T @ checked["head"][:3, :3], np.eye(3), atol=1e-12)
        np.testing.assert_array_equal(checked["head"][:3, 3], head[:3, 3])
        self.assertLess(np.max(np.abs(checked["head"][:3, :3] - raw)), .001)
        self.assertEqual(state["head_pose"]["m"], head.reshape(-1).tolist())
        self.daemon.state = state
        receipt = await self.motion.submit("attention", "probe", 10)
        self.assertEqual((await self.motion.wait(receipt.request_id)).status, "completed")

    async def test_projection_rejects_scale_shear_reflection_and_bad_bottom_row(self):
        for index, value in ((0, 1.02), (1, .1), (10, -1), (15, .9)):
            state = copy.deepcopy(self.daemon.state)
            head = np.eye(4).reshape(-1).tolist()
            head[index] = value
            state["head_pose"]["m"] = head
            with self.assertRaises(ValueError):
                checked_pose(state)


class MicroWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_goto_and_hold_only_measured_values(self):
        daemon = MicroDaemon()
        requests = []

        def handle(request):
            requests.append(request)
            path = request.url.path
            if path.endswith("/daemon/status"):
                return httpx.Response(200, json={"state": "running", "error": None, "ready": False})
            if path.endswith("/move/running"):
                return httpx.Response(200, json=[])
            if path.endswith("/state/full"):
                return httpx.Response(200, json=daemon.state)
            if path.endswith("/set_target"):
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(200, json={"uuid": str(uuid4())})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            session = _Session("http://fake", client, None)
            await session.snapshot()
            await session.start({"_goto": {"head_pose": daemon.state["head_pose"], "duration": 1.5}})
            await session.hold_current()
        import json
        held = json.loads(requests[-1].content)
        np.testing.assert_allclose(held["target_head_pose"]["m"], checked_pose(daemon.state)["head"].reshape(-1), atol=1e-12)
        self.assertEqual(held["target_antennas"], [.23, -.14])
        self.assertEqual(held["target_body_yaw"], .08)
        self.assertTrue(any(r.url.path.endswith("/move/goto") for r in requests))

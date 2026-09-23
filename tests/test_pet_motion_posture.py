import asyncio
import copy
import time
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

import numpy as np

from pet_motion import MotionExecutor
from pet_motion.posture import diagnostic_pose
from pet_motion.micro import checked_pose, target_pose
from pet_motion.transport import _Session
from test_pet_motion_micro import MicroDaemon


class PostureDaemon(MicroDaemon):
    def __init__(self):
        super().__init__()
        self.offsets = [0.]*6
        self.joints = [.08, .1, .2, .3, .4, .5, .6]
        self.targets = self.joints.copy()
        self.pin_calls = 0
        self.ik_required = True

    async def diagnostics(self):
        state = await self.snapshot()
        return {"schema_version":1,"read_only":True,"stable_read":True,
                "timestamp":time.time(),"error":None,"control_mode":"enabled",
                "active_move_depth":0,"head_pose":np.array(state["head_pose"]["m"]).reshape(4,4).tolist(),
                "head_joints":self.joints.copy(),"target_head_joints":self.targets.copy(),
                "antennas":state["antennas_position"],"speech_offsets":self.offsets.copy(),
                "ik_required":self.ik_required}

    async def pin_current_joints(self):
        assert not self.active_uuid
        self.pin_calls += 1
        self.targets = self.joints.copy()
        self.ik_required = False


class PostureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.daemon = PostureDaemon()
        self.motion = MotionExecutor(self.daemon, dry_run=False)
        for semantic in ("look_up","return_to_start"):
            self.motion.mappings[semantic]["approved"] = True
        self.motion.posture_profiles["look_up"]["approved"] = True
        await self.motion.set_turn("session:one")

    async def asyncTearDown(self):
        await self.motion.close()

    async def action(self, semantic="look_up", **kwargs):
        receipt = await self.motion.submit(semantic,"session:one",2.5,
            execution_budget_seconds=10,**kwargs)
        return await self.motion.wait(receipt.request_id)

    async def test_look_up_holds_and_explicit_return_uses_baseline(self):
        origin=copy.deepcopy(self.daemon.state)
        result=await self.action()
        self.assertEqual(result.status,"completed")
        self.assertEqual(result.reason,"holding_verified")
        self.assertIsNotNone(result.baseline_id)
        self.assertEqual(len(self.daemon.starts),1)
        # Baseline can span an utterance epoch but is explicitly named.
        await self.motion.set_turn("session:two")
        self.assertEqual(self.daemon.pin_calls,0)
        receipt=await self.motion.submit("return_to_start","session:two",2.5,
            execution_budget_seconds=10,baseline_id=result.baseline_id)
        returned=await self.motion.wait(receipt.request_id)
        self.assertEqual(returned.reason,"returned_to_measured_start")
        self.assertIsNone(self.motion._baseline)
        np.testing.assert_allclose(self.daemon.state["head_pose"]["m"],origin["head_pose"]["m"],atol=1e-12)

    async def test_duplicate_look_up_does_not_accumulate_angle(self):
        first=await self.action()
        second=await self.action()
        self.assertEqual(second.reason,"already_looking_up")
        self.assertEqual(first.baseline_id,second.baseline_id)
        self.assertEqual(len(self.daemon.starts),1)

    async def test_stop_during_move_pins_without_return_or_baseline(self):
        self.daemon.auto_complete=False
        receipt=await self.motion.submit("look_up","session:one",2.5,execution_budget_seconds=10)
        await self.daemon.started.wait()
        await self.motion.cancel()
        self.assertEqual((await self.motion.wait(receipt.request_id)).status,"cancelled")
        self.assertEqual(len(self.daemon.starts),1)
        self.assertEqual(self.daemon.pin_calls,1)
        self.assertIsNone(self.motion._baseline)

    async def test_stop_after_verified_hold_retains_baseline(self):
        first=await self.action()
        await self.motion.cancel()
        self.assertEqual(self.daemon.pin_calls,1)
        self.assertEqual(self.motion._baseline.id,first.baseline_id)
        self.assertEqual(len(self.daemon.starts),1)

    async def test_unknown_and_expired_baseline_rejected(self):
        self.assertEqual((await self.action("return_to_start")).reason,"baseline_missing_or_invalid")
        first=await self.action()
        self.assertEqual((await self.action("return_to_start",baseline_id="wrong")).reason,"baseline_missing_or_invalid")
        self.motion._baseline.expires=time.monotonic()-1
        self.assertEqual((await self.action("return_to_start",baseline_id=first.baseline_id)).reason,"baseline_missing_or_invalid")
        self.assertEqual(len(self.daemon.starts),1)
        self.assertEqual((await self.action()).reason,"baseline_expired_requires_review")

    async def test_interrupted_look_up_reuses_private_origin_not_new_angle(self):
        self.daemon.auto_complete=False
        receipt=await self.motion.submit("look_up","session:one",2.5,execution_budget_seconds=10)
        await self.daemon.started.wait()
        original_target=copy.deepcopy(self.daemon.starts[0][1]["head_pose"])
        halfway=target_pose(checked_pose(self.daemon.origin),
                            {**self.motion.posture_profiles["look_up"],"delta_degrees":-.75})
        self.daemon.state["head_pose"]={"m":halfway["head"].reshape(-1).tolist()}
        await self.motion.cancel()
        self.assertEqual((await self.motion.wait(receipt.request_id)).status,"cancelled")
        self.daemon.auto_complete=True
        result=await self.action()
        self.assertEqual(result.status,"completed")
        np.testing.assert_allclose(self.daemon.starts[1][1]["head_pose"]["m"],original_target["m"],atol=1e-12)

    async def test_residual_offset_blocks_all_motion(self):
        self.daemon.offsets[3]=.01
        result=await self.action()
        self.assertEqual(result.status,"failed")
        self.assertEqual(self.daemon.starts,[])
        self.assertFalse(self.motion.available)

    async def test_existing_tracking_error_blocks_new_target(self):
        self.daemon.targets[2]+=.02
        result=await self.action()
        self.assertEqual(result.reason,"existing_joint_target_not_reached")
        self.assertEqual(self.daemon.starts,[])

    async def test_failed_arrival_never_issues_baseline(self):
        self.daemon.skip_motion=True
        result=await self.action()
        self.assertEqual(result.status,"failed")
        self.assertIsNone(result.baseline_id)
        self.assertEqual(len(self.daemon.starts),1)
        self.assertEqual(self.daemon.pin_calls,1)

    async def test_dry_run_has_no_real_baseline(self):
        self.motion.dry_run=True
        result=await self.action()
        self.assertEqual(result.status,"dry_run")
        self.assertIsNone(result.baseline_id)
        self.assertEqual(self.daemon.starts,[])

    async def test_diagnostics_reject_missing_offsets_targets_and_stale_read(self):
        good=await self.daemon.diagnostics()
        for change in ({"speech_offsets":None},{"target_head_joints":None},
                       {"timestamp":time.time()-2},{"stable_read":False}):
            with self.assertRaises(ValueError):
                diagnostic_pose({**good,**change})


class JointPinWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_fire_and_forget_verified_by_target_and_actual_without_ack(self):
        daemon=PostureDaemon()
        sent=[]
        class Socket:
            async def send(self, raw):
                import json
                payload=json.loads(raw)
                sent.append(payload)
                daemon.targets=payload["joints"]
                daemon.ik_required=False
        @asynccontextmanager
        async def connect(*args, **kwargs):
            yield Socket()
        session=_Session("http://fake",None,None)
        session.diagnostics=daemon.diagnostics
        with patch("pet_motion.transport.connect",connect):
            await session.pin_current_joints()
        self.assertEqual(sent,[{"type":"set_head_joints","joints":daemon.joints}])
        self.assertFalse(daemon.ik_required)

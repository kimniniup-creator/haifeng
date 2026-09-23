import asyncio
import copy
import time
import unittest
from pet_motion import MotionExecutor
from test_pet_motion_posture import PostureDaemon

class IndependentPostureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.daemon=PostureDaemon()
        self.motion=MotionExecutor(self.daemon,dry_run=False)
        for name in ('look_up','return_to_start'): self.motion.mappings[name]['approved']=True
        self.motion.posture_profiles['look_up']['approved']=True
        await self.motion.set_turn('session:one')

    async def asyncTearDown(self): await self.motion.close()

    async def action(self):
        r=await self.motion.submit('look_up','session:one',2.5,execution_budget_seconds=10)
        return await self.motion.wait(r.request_id)

    async def test_repeat_must_reject_target_tracking_error(self):
        first=await self.action()
        self.assertEqual(first.status,'completed')
        self.daemon.targets[2]+=.02
        repeated=await self.action()
        self.assertNotEqual(repeated.status,'completed',repr(repeated))

    async def test_idle_stop_caller_cancel_cannot_release_unverified_hold(self):
        await self.action()
        self.motion.stop_timeout = .1
        entered=asyncio.Event()
        async def incomplete_pin():
            entered.set()
            await asyncio.Event().wait()
        self.daemon.pin_current_joints=incomplete_pin
        caller=asyncio.create_task(self.motion.cancel())
        await entered.wait()
        caller.cancel()
        await asyncio.sleep(.02)
        unsafe=caller.done() and self.motion.available and self.motion._baseline is not None
        if caller.done():
            try: await caller
            except asyncio.CancelledError: pass
        self.assertFalse(unsafe,'cancel caller abandoned hold verification, cleared stopping, retained baseline and availability')
        # The original bounded hold is still running; wait for its configured
        # timeout and confirm that cancellation is propagated only after fault.
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertEqual(self.motion.fault, 'posture_hold_unconfirmed')
        self.assertIsNone(self.motion._baseline)
        self.assertFalse(self.motion.available)

    async def test_idle_stop_cancellation_waits_for_successful_hold(self):
        first = await self.action()
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed_pin():
            entered.set()
            await release.wait()
        self.daemon.pin_current_joints = delayed_pin
        caller = asyncio.create_task(self.motion.cancel())
        await entered.wait()
        caller.cancel()
        await asyncio.sleep(.02)
        self.assertFalse(caller.done())
        self.assertFalse(self.motion.available)
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(self.motion.available)
        self.assertEqual(self.motion._baseline.id, first.baseline_id)

    async def test_repeat_checks_tracking_through_stability_window(self):
        await self.action()
        async def change_target():
            await asyncio.sleep(.2)
            self.daemon.targets[2] += .02
        disturbance = asyncio.create_task(change_target())
        repeated = await self.action()
        await disturbance
        self.assertEqual(repeated.reason, 'existing_hold_not_verified')
        self.assertIsNone(self.motion._baseline)
        self.assertEqual(len(self.daemon.starts), 1)

    async def test_session_invalidation_blocks_old_origin_reissue(self):
        first = await self.action()
        seed = self.motion._posture_seed
        await self.motion.invalidate_baseline()
        await self.motion.set_turn('session:two')
        repeated = await self.motion.submit('look_up', 'session:two', 10)
        self.assertEqual(repeated.reason, 'posture_session_invalidated_requires_review')
        self.assertIsNone(self.motion._baseline)
        self.assertIs(self.motion._posture_seed, seed)
        returned = await self.motion.submit('return_to_start', 'session:two', 10, baseline_id=first.baseline_id)
        self.assertEqual(returned.status, 'rejected')
        self.assertEqual(len(self.daemon.starts), 1)

    async def test_session_invalidated_before_first_receipt_never_reissues_seed(self):
        self.daemon.auto_complete = False
        receipt = await self.motion.submit('look_up', 'session:one', 10)
        await self.daemon.started.wait()
        await self.motion.invalidate_baseline()
        self.assertEqual((await self.motion.wait(receipt.request_id)).status, 'cancelled')
        self.assertIsNotNone(self.motion._posture_seed)
        self.assertIsNone(self.motion._baseline)
        await self.motion.set_turn('session:two')
        second = await self.motion.submit('look_up', 'session:two', 10)
        self.assertEqual(second.reason, 'posture_session_invalidated_requires_review')
        self.assertEqual(len(self.daemon.starts), 1)

    async def test_session_change_before_any_posture_does_not_lock(self):
        await self.motion.invalidate_baseline()
        self.assertFalse(self.motion._posture_session_invalidated)
        self.assertEqual((await self.action()).status, 'completed')

    async def test_owner_review_requires_original_pose_even_after_seed_expiry(self):
        origin = copy.deepcopy(self.daemon.state)
        await self.action()
        await self.motion.invalidate_baseline()
        await self.motion.invalidate_baseline()
        self.motion._posture_seed.expires = time.monotonic()-1
        self.assertFalse(await self.motion.review_reset_posture_baseline())
        self.assertTrue(self.motion._posture_session_invalidated)
        self.daemon.state = origin
        self.assertTrue(await self.motion.review_reset_posture_baseline())
        self.assertIsNone(self.motion._posture_seed)
        self.assertFalse(self.motion._posture_session_invalidated)
        self.assertEqual(len(self.daemon.starts), 1)

    async def test_invalidation_caller_cancel_keeps_retirement_after_hold_timeout(self):
        await self.action()
        self.motion.stop_timeout = .1
        entered = asyncio.Event()
        async def stuck_pin():
            entered.set()
            await asyncio.Event().wait()
        self.daemon.pin_current_joints = stuck_pin
        caller = asyncio.create_task(self.motion.invalidate_baseline())
        await entered.wait()
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(self.motion._posture_session_invalidated)
        self.assertIsNone(self.motion._baseline)
        self.assertFalse(self.motion.available)
        self.assertFalse(await self.motion.review_reset_posture_baseline())

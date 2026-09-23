import asyncio
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

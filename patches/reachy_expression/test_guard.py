import asyncio
import logging
import threading
import unittest
from types import SimpleNamespace
import numpy as np
from fastapi import HTTPException
import haifeng_expression_guard as guard
from reachy_mini.daemon.app.routers import move as router

class Backend:
    def __init__(self):
        self.error=None; self.ready=threading.Event(); self.ready.set()
        self.mode='enabled'; self.is_move_running=False
        self.h=np.eye(4); self.a=np.zeros(2); self.y=0.
        self.logger=logging.getLogger('test'); self.sounds=[]; self.writes=[]
        self.behavior='normal'; self._active_move_depth=0; self._stop_move_requested=False
    def get_motor_control_mode(self): return self.mode
    def get_present_head_pose(self): return self.h
    def get_present_antenna_joint_positions(self): return self.a
    def get_present_body_yaw(self): return self.y
    def set_target_head_pose(self,v): self.h=v.copy(); self.writes.append('head')
    def set_target_antenna_joint_positions(self,v): self.a=v.copy(); self.writes.append('antenna')
    def set_target_body_yaw(self,v): self.y=v; self.writes.append('body')
    def play_sound(self,v): self.sounds.append(v)
    def stop_sound(self): self.sounds.append('stop')
    async def play_move(self,m):
        if self.behavior=='skip': return
        self.is_move_running=True
        try:
            for t in np.linspace(0,m.duration,50):
                h,a,y=m.evaluate(t)
                self.h,self.a,self.y=h,a,y
                if self.behavior=='disconnect': self.error='USB disconnected'
                if self.behavior=='wait': await asyncio.sleep(100)
        finally: self.is_move_running=False

class Move:
    duration=1.
    sound_path='expression.wav'
    def evaluate(self,t):
        h=np.eye(4);h[0,3]=.001+.002*t
        return h,np.array([.1+t*.05,-.1]),.02

class Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.b=Backend(); router.move_tasks.clear()
    async def test_return_and_audio(self):
        m=guard.ReturningMove(self.b,Move())
        np.testing.assert_allclose(m.evaluate(0)[0],self.b.h)
        self.assertEqual(self.b.sounds,[])
        await guard.execute(self.b,m)
        self.assertTrue(guard.at_rest(self.b,m.rest))
        self.assertEqual(self.b.sounds,['expression.wav','stop'])
    async def test_busy_rejected(self):
        first=guard.start_expression(self.b,Move(),router.create_move_task,router.move_tasks)
        with self.assertRaises(HTTPException) as ctx:
            guard.start_expression(self.b,Move(),router.create_move_task,router.move_tasks)
        self.assertEqual(ctx.exception.status_code,409)
        await router.move_tasks[first.uuid]; await asyncio.sleep(0)
        self.assertFalse(self.b._haifeng_expression_reserved)
    async def test_cancel_before_start_releases(self):
        result=guard.start_expression(self.b,Move(),router.create_move_task,router.move_tasks)
        task=router.move_tasks[result.uuid];task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        await asyncio.sleep(0)
        self.assertFalse(self.b._haifeng_expression_reserved)
        self.assertFalse(router.move_tasks);self.assertFalse(self.b.writes)
    async def test_cancel_during_motion_holds_measured_pose(self):
        self.b.behavior='wait';m=guard.ReturningMove(self.b,Move())
        task=asyncio.create_task(guard.execute(self.b,m));await asyncio.sleep(0);task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(len(self.b.writes),3)
    async def test_disconnect_stops_without_return_writes(self):
        self.b.behavior='disconnect';m=guard.ReturningMove(self.b,Move())
        with self.assertRaises(RuntimeError): await guard.execute(self.b,m)
        self.assertFalse(self.b.writes)
    async def test_disabled_rejects(self):
        self.b.mode='disabled'
        with self.assertRaises(HTTPException):
            guard.start_expression(self.b,Move(),router.create_move_task,router.move_tasks)
        self.assertFalse(router.move_tasks)
    async def test_silent_skip_is_failure(self):
        self.b.behavior='skip';m=guard.ReturningMove(self.b,Move())
        with self.assertRaisesRegex(RuntimeError,'skipped'): await guard.execute(self.b,m)
        self.assertFalse(self.b.writes)
    async def test_busy_backend_does_not_change_targets(self):
        m=guard.ReturningMove(self.b,Move());self.b.is_move_running=True
        with self.assertRaises(RuntimeError): await guard.execute(self.b,m)
        self.assertFalse(self.b.writes)
    async def test_invalid_target_rejects(self):
        move=Move();move.duration=float('nan')
        with self.assertRaises(HTTPException):
            guard.start_expression(self.b,move,router.create_move_task,router.move_tasks)

    async def test_actual_sdk_play_loop_returns_and_unlocks(self):
        from reachy_mini.daemon.backend.abstract import Backend as NativeBackend
        def acquire():
            if self.b.is_move_running: return False
            self.b.is_move_running=True
            self.b._active_move_depth=1
            return True
        self.b._try_start_move=acquire
        self.b._end_move=lambda: setattr(self.b,'is_move_running',False)
        self.b.play_move=lambda m: NativeBackend.play_move(self.b,m,play_frequency=30)
        m=guard.ReturningMove(self.b,Move())
        await guard.execute(self.b,m)
        self.assertFalse(self.b.is_move_running)
        self.assertTrue(guard.at_rest(self.b,m.rest))

    async def test_installed_route_calls_guard(self):
        from unittest.mock import patch
        with patch.object(router,'RecordedMoves',return_value=SimpleNamespace(get=lambda n:Move())):
            result=await router.play_recorded_move_dataset('test','test',self.b)
            self.assertTrue(self.b._haifeng_expression_reserved)
            await router.move_tasks[result.uuid]
            await asyncio.sleep(0)
            self.assertFalse(self.b._haifeng_expression_reserved)

    async def test_native_stop_does_not_reset(self):
        async def stopped(m):
            m.evaluate(.2)
            self.b.a=np.array([.02,.01])
            self.b._stop_move_requested=True
        self.b.play_move=stopped
        m=guard.ReturningMove(self.b,Move())
        with self.assertRaises(asyncio.CancelledError): await guard.execute(self.b,m)
        np.testing.assert_allclose(self.b.a,[.02,.01])

if __name__=='__main__': unittest.main()

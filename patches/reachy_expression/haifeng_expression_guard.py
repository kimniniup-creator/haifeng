"""Local Reachy 1.8.0/1.11.0 recorded-expression transaction; no firmware changes."""
import asyncio
import math
import numpy as np
from fastapi import HTTPException
from reachy_mini.motion.goto import GotoMove
from reachy_mini.utils.interpolation import InterpolationTechnique


def pose(backend):
    return (np.array(backend.get_present_head_pose(), dtype=float, copy=True),
            np.array(backend.get_present_antenna_joint_positions(), dtype=float, copy=True),
            float(backend.get_present_body_yaw()))


def healthy(backend):
    mode = backend.get_motor_control_mode()
    mode = getattr(mode, 'value', mode)
    if backend.error or not backend.ready.is_set() or mode != 'enabled':
        raise RuntimeError('Expression stopped: robot disconnected or motors disabled')


def checked(value):
    head, antennas, yaw = value
    if head is None or antennas is None or yaw is None:
        raise ValueError('Recorded expression must include full body targets')
    head, antennas, yaw = np.asarray(head), np.asarray(antennas), float(yaw)
    if head.shape != (4, 4) or antennas.shape != (2,) or not all(
            np.isfinite(x).all() for x in (head, antennas, yaw)):
        raise ValueError('Invalid expression target')
    return head.copy(), antennas.copy(), yaw


def rotation_error(a, b):
    return math.acos(float(np.clip((np.trace(a[:3, :3].T @ b[:3, :3])-1)/2, -1, 1)))


def transition(a, b):
    angle = max(rotation_error(a[0], b[0]), float(np.max(np.abs(a[1]-b[1]))), abs(a[2]-b[2]))
    distance = float(np.linalg.norm(a[0][:3, 3]-b[0][:3, 3]))
    # minjerk peak speed is 1.875x average. Limit transition to ~30 deg/s, 2 cm/s.
    duration = max(2.0, 1.9*angle/math.radians(30), 1.9*distance/.02)
    if duration > 15:
        raise ValueError('Transition too large; inspect robot pose before expression')
    return GotoMove(a[0], b[0], a[1], b[1], a[2], b[2], duration,
                    InterpolationTechnique.MIN_JERK)


class ReturningMove:
    """One move lock spans entry, original expression, and return to measured rest pose."""
    sound_path = None

    def __init__(self, backend, move):
        healthy(backend)
        self.backend, self.move = backend, move
        self.rest = checked(pose(backend))
        if not math.isfinite(move.duration) or not 0 < move.duration <= 90:
            raise ValueError('Expression duration outside supported bounds')
        self.entry = transition(self.rest, checked(move.evaluate(0)))
        self.exit = transition(checked(move.evaluate(np.nextafter(move.duration, 0))), self.rest)
        self.duration = self.entry.duration + move.duration + self.exit.duration
        self.sound_started = False
        self.has_evaluated = False

    def evaluate(self, t):
        healthy(self.backend)
        self.has_evaluated = True
        if t < self.entry.duration:
            return self.entry.evaluate(max(0, t))
        elapsed = t-self.entry.duration
        if elapsed < self.move.duration:
            if not self.sound_started:
                self.sound_started = True
                if self.move.sound_path is not None:
                    self.backend.play_sound(str(self.move.sound_path))
            return checked(self.move.evaluate(elapsed))
        return self.exit.evaluate(min(self.exit.duration, elapsed-self.move.duration))


def at_rest(backend, rest):
    actual = checked(pose(backend))
    return (np.linalg.norm(actual[0][:3, 3]-rest[0][:3, 3]) <= .006
            and rotation_error(actual[0], rest[0]) <= .04
            and np.max(np.abs(actual[1]-rest[1])) <= .04
            and abs(actual[2]-rest[2]) <= .04)


async def execute(backend, transaction):
    try:
        healthy(backend)
        if backend.is_move_running:
            raise RuntimeError('Another motion owns the robot; expression not started')
        async with asyncio.timeout(transaction.duration+4):
            await backend.play_move(transaction)
            if getattr(backend, '_stop_move_requested', False):
                raise asyncio.CancelledError('Native stop requested')
            if not transaction.has_evaluated:
                raise RuntimeError('Backend skipped expression; another motion may own the robot')
            healthy(backend)
            # Original play loop ends just short of duration; pin the exact final target.
            h, a, y = transaction.rest
            backend.set_target_head_pose(h)
            backend.set_target_antenna_joint_positions(a)
            backend.set_target_body_yaw(y)
            for _ in range(20):
                healthy(backend)
                if at_rest(backend, transaction.rest):
                    return
                await asyncio.sleep(.1)
            raise RuntimeError('Expression ended but return pose not reached; inspect motors')
    except BaseException:
        # Stop means stop, never secretly continue a return animation after cancellation.
        if transaction.has_evaluated and not backend.error and backend.ready.is_set():
            h, a, y = pose(backend)
            backend.set_target_head_pose(h)
            backend.set_target_antenna_joint_positions(a)
            backend.set_target_body_yaw(y)
        raise
    finally:
        try:
            backend.stop_sound()
        except Exception:
            backend.logger.warning('Could not stop expression audio', exc_info=True)


def start_expression(backend, move, create_move_task, move_tasks):
    if getattr(backend, '_haifeng_expression_reserved', False) or backend.is_move_running or move_tasks:
        raise HTTPException(409, 'Previous motion/return still running; wait or stop it first')
    try:
        transaction = ReturningMove(backend, move)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(503, str(e)) from e
    token = object()
    backend._haifeng_expression_reserved = token
    coro = execute(backend, transaction)
    try:
        result = create_move_task(coro)
        task = move_tasks[result.uuid]

        def release(done):
            # Also runs if the native wrapper was cancelled before awaiting execute.
            coro.close()
            move_tasks.pop(result.uuid, None)
            if getattr(backend, '_haifeng_expression_reserved', None) is token:
                backend._haifeng_expression_reserved = False

        task.add_done_callback(release)
        return result
    except BaseException:
        backend._haifeng_expression_reserved = False
        coro.close()
        raise

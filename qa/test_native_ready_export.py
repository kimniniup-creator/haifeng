"""Offline only: QA_NATIVE_BACKEND points to audited source; no SDK imports."""
import ast
import os
from pathlib import Path
import threading
from types import SimpleNamespace
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get('QA_NATIVE_BACKEND'),
                                reason='Explicit audited offline source path required')


def candidate():
    source = Path(os.environ['QA_NATIVE_BACKEND']) / 'robot/backend.py'
    tree = ast.parse(source.read_bytes())
    node = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == 'get_status')
    node.returns = None
    node.decorator_list = []
    for arg in node.args.args:
        arg.annotation = None
    node.body[1:1] = ast.parse(
        'self._status.ready = self.ready.is_set()\n'
        'self._status.last_alive = self.last_alive').body
    scope = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 'qa-memory-candidate', 'exec'), scope)
    return scope['get_status']


def backend():
    return SimpleNamespace(ready=threading.Event(), last_alive=None,
                           error=None, motor_control_mode='disabled',
                           _status=SimpleNamespace(ready=False, last_alive=None))


def test_set_is_not_health_and_does_not_hide_error_or_staleness():
    b = backend()
    b.ready.set()
    b.last_alive = 1.0
    b.error = 'motor timeout'
    s = candidate()(b)
    assert s.ready is True and s.last_alive == 1.0
    assert s.error == 'motor timeout' and s.motor_control_mode == 'disabled'


def test_unknown_timestamp_not_synthesized_and_clear_keeps_real_timestamp():
    b = backend()
    b.ready.set()
    get = candidate()
    assert get(b).ready is True and get(b).last_alive is None
    b.ready.clear()
    b.last_alive = 123.0
    assert get(b).ready is False and get(b).last_alive == 123.0


def test_completed_writer_transitions_visible_to_reader():
    b = backend()
    get = candidate()
    def write(value):
        b.last_alive = value
        (b.ready.set if value is not None else b.ready.clear)()
    for value in (123.0, None, 456.0):
        worker = threading.Thread(target=write, args=(value,))
        worker.start()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert get(b).ready is (value is not None)
        assert get(b).last_alive == value


def test_export_is_shared_mutable_object_not_immutable_snapshot():
    b = backend()
    get = candidate()
    first = get(b)
    b.ready.set()
    b.last_alive = 200.0
    second = get(b)
    assert first is second
    assert first.ready is True and first.last_alive == 200.0

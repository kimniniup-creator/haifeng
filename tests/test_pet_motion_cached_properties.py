import pytest
from pet_motion.telemetry import snapshot
from pet_motion.telemetry import cached_scalar
from test_pet_motion_telemetry import backend

@pytest.mark.parametrize('field',['_torque_enabled','_current_head_operation_mode','_current_antennas_operation_mode','last_alive'])
def test_cached_fields_never_execute_properties(field):
    touched=[]
    def getter(self):
        touched.append(field)
        raise AssertionError('descriptor executed')
    cls=type('CachedBackend',(),{field:property(getter)})
    b=cls(); b.__dict__.update(vars(backend()))
    try: snapshot(b)
    except (ValueError,TypeError): pass
    assert not touched

def test_static_scalar_never_calls_dynamic_getters_or_conversion():
    class Hostile:
        def __getattribute__(self, name):
            raise AssertionError('dynamic lookup')
        def __getattr__(self, name):
            raise AssertionError('fallback lookup')
    obj = Hostile()
    object.__setattr__(obj, '_torque_enabled', True)
    assert cached_scalar(obj, '_torque_enabled', bool) is True
    assert cached_scalar(obj, 'missing', int) is None
    class Converter:
        def tolist(self):
            raise AssertionError('conversion')
    object.__setattr__(obj, 'value', Converter())
    assert cached_scalar(obj, 'value', float) is None

def test_static_scalar_rejects_wrong_types_and_nonfinite():
    b = backend()
    b.flag = 1
    b.mode = True
    b.stamp = float('nan')
    assert cached_scalar(b, 'flag', bool) is None
    assert cached_scalar(b, 'mode', int) is None
    assert cached_scalar(b, 'stamp', float) is None

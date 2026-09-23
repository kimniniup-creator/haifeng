import math
import pytest
from pet_vision import GestureEngine, Hand, Observation
from pet_vision.synthetic import open_hand, demo_observations
from pet_vision.pipeline import Frame, Pipeline, LocalEventSink


def feed(engine, xs, start=100, label_flip=False, confidence=.9):
    events = []
    for i,x in enumerate(xs):
        t=start+i*.1
        h=open_hand(x,confidence,"Right" if label_flip and i%2 else "Left")
        events += engine.update(Observation(t,(h,)),now=t)
    return events


def test_demo_contract_and_leave_reset():
    engine=GestureEngine()
    events=[e for obs in demo_observations(100) for e in engine.update(obs,now=obs.observed_at)]
    assert [e['kind'] for e in events] == ['palm_stop','presence','presence','presence','wave']
    assert [e['payload']['present'] for e in events if e['kind']=='presence'] == [True,False,True]
    assert all(e['source']=='vision' and e['schema_version']==1 and e['ttl_seconds']<=30 for e in events)
    assert len({e['event_id'] for e in events}) == len(events)


def test_held_palm_once_and_jitter_not_wave():
    events=feed(GestureEngine(),[.003*(i%2) for i in range(80)],label_flip=True)
    assert [e['kind'] for e in events].count('palm_stop')==1
    assert not any(e['kind']=='wave' for e in events)


def test_wave_with_handedness_flip_and_cooldown():
    events=feed(GestureEngine(),[0,.06,.12,.06,0,-.06,0,.06,.12]*2,label_flip=True)
    assert [e['kind'] for e in events].count('wave')==1
    assert not any(e['kind']=='palm_stop' for e in events)


@pytest.mark.parametrize('t,now',[(100,102),(102,100),(float('nan'),100),(100,float('inf'))])
def test_bad_timestamps_do_not_advance(t,now):
    engine=GestureEngine()
    assert engine.update(Observation(t,(open_hand(),)),now=now)==[]
    assert engine.last_timestamp == float('-inf')


def test_duplicate_frame_and_low_confidence():
    engine=GestureEngine()
    obs=Observation(100,(open_hand(),))
    engine.update(obs,now=100)
    assert engine.update(obs,now=100.1)==[]
    rejected=feed(GestureEngine(),[0]*10,confidence=.3)
    assert all(e['kind']=='presence' and e['payload']['present'] is False for e in rejected)


def test_crossing_two_hands_do_not_count_as_wave():
    engine=GestureEngine()
    events=[]
    for i in range(15):
        t=100+i*.1
        hands=(open_hand(-.25+i*.02),open_hand(.25-i*.02))
        events+=engine.update(Observation(t,hands if i%2 else hands[::-1]),now=t)
    assert not any(e['kind']=='wave' for e in events)


def test_gap_does_not_complete_held_palm():
    engine=GestureEngine()
    feed(engine,[0,0,0])
    assert engine.update(Observation(104,(open_hand(),)),now=104)==[]


def test_malformed_landmarks():
    assert not Hand(((math.nan,0,0),)*21,.9).valid()
    assert not Hand(((0,0,0),),.9).valid()


def test_pipeline_rejects_stale_before_detection_and_after_inference():
    class Fake:
        called=0
        def detect(self,frame,t):
            self.called+=1
            return Observation(t,(open_hand(),))
    detector=Fake()
    p=Pipeline(detector,GestureEngine(),lambda e:None,lambda:103)
    assert p.process(Frame(None,100))==[]
    assert detector.called==0
    times=iter([100,103])
    p.clock=lambda:next(times)
    assert p.process(Frame(None,100))==[]
    assert p.engine.last_timestamp==float('-inf')


def test_sink_rejects_remote_and_missing_token(monkeypatch):
    monkeypatch.delenv('PET_VISION_TOKEN',raising=False)
    with pytest.raises(ValueError): LocalEventSink('https://example.com',token='fake')
    with pytest.raises(ValueError): LocalEventSink()


def test_real_model_blank_frame_when_installed():
    from pathlib import Path
    model=Path('.runtime/models/hand_landmarker.task')
    if not model.exists(): pytest.skip('Run tools/run_pet_vision_setup.py for optional real model smoke')
    np=pytest.importorskip('numpy')
    pytest.importorskip('mediapipe')
    from pet_vision.detector import MediaPipeDetector
    detector=MediaPipeDetector(model)
    try:
        assert detector.detect(np.zeros((240,320,3),dtype=np.uint8),100).hands==()
    finally:
        detector.close()


def test_palm_at_five_fps():
    engine=GestureEngine()
    events=[]
    for i in range(8):
        t=100+i*.2
        events+=engine.update(Observation(t,(open_hand(),)),now=t)
    assert sum(e['kind']=='palm_stop' for e in events)==1


def test_fresh_empty_frames_reset_presence_and_track():
    engine=GestureEngine()
    feed(engine,[0]*6)
    events=[]
    for i in range(6,14):
        t=100+i*.1
        events+=engine.update(Observation(t),now=t)
    assert [e['payload']['present'] for e in events]==[False]
    assert not engine.tracks and not engine.present
    assert engine.update(Observation(101.4,(open_hand(),)),now=101.4)==[]


def test_local_http_delivery_preserves_contract():
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path,self.headers.get('Authorization'),json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"accepted"}')
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.handle_request)
    thread.start()
    event=feed(GestureEngine(),[0]*6)[0]
    try:
        sink=LocalEventSink(f'http://127.0.0.1:{server.server_port}/v1/events',token='test-only')
        assert sink(event)=={'status':'accepted'}
        thread.join(2)
        assert received==[('/v1/events','Bearer test-only',event)]
    finally:
        server.server_close()


def test_presence_lease_refresh_is_fresh_and_stops_without_input():
    engine=GestureEngine()
    events=feed(engine,[0]*60)
    presence=[e for e in events if e['kind']=='presence']
    assert len(presence)>=6
    assert all(e['payload']['present'] for e in presence)
    assert all(b['observed_at']-a['observed_at']<=.9 for a,b in zip(presence,presence[1:]))
    last=engine.last_timestamp
    assert engine.update(Observation(last,(open_hand(),)),now=last+4)==[]
    assert engine.last_timestamp==last


def test_sink_selects_vision_role_token(monkeypatch):
    monkeypatch.setenv('PET_API_TOKEN','operator-test-only')
    monkeypatch.setenv('PET_VISION_TOKEN','vision-test-only')
    assert LocalEventSink().token=='vision-test-only'


def test_async_sink_is_rejected_instead_of_silently_lost():
    async def async_sink(event): pass
    with pytest.raises(TypeError,match='synchronous'):
        Pipeline(None,GestureEngine(),async_sink)


@pytest.mark.parametrize('seconds', [0, -1, 61, float('nan'), float('inf')])
def test_camera_window_rejects_invalid_duration_before_start(seconds, monkeypatch):
    from pet_vision import ipc
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid duration must not open a camera process')
    monkeypatch.setattr(ipc.subprocess, 'Popen', forbidden)
    with pytest.raises(ValueError, match='Camera window'):
        list(ipc.frames(opencv=True, seconds=seconds))


def test_camera_provider_forwards_bounded_window(monkeypatch):
    from pet_vision import ipc
    calls = []
    def fake_frames(**kwargs):
        calls.append(kwargs)
        return iter(())
    monkeypatch.setattr(ipc, 'frames', fake_frames)
    list(ipc.leased_opencv_frames(seconds=60))
    list(ipc.leased_video_frames())
    assert calls == [{'opencv': True, 'seconds': 60}, {'direct': True, 'seconds': 15}]

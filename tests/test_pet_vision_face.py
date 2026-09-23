import pytest
from pet_vision.face_cues import FaceCueEngine,FaceObservation,FaceSample


QUALITY={'usable':True,'reasons':[]}


def face(smile=.8,**coefficients):
    return FaceSample((.3,.2,.7,.8),{'mouthSmileLeft':smile,'mouthSmileRight':smile,**coefficients},dict(QUALITY))


def feed(engine,sample,*,start=100,count=10,step=.2):
    return [event for i in range(count) for event in engine.update(
        FaceObservation(start+i*step,() if sample is None else (sample,),dict(QUALITY)),now=start+i*step)]


def cues(events): return [e for e in events if e['kind']=='visual_cue']


def test_smile_stable_once_and_semantic_contract():
    events=feed(FaceCueEngine(),face(),count=100)
    result=cues(events)
    assert len(result)==1
    payload=result[0]['payload']
    assert payload['cue_name']=='smile' and payload['stable_ms']>=800
    assert payload['confidence_basis']=='configured_detection_floor'
    assert payload['quality']['usable'] and payload['attribution']=='single_face'
    assert result[0]['confidence']==.7 and result[0]['ttl_seconds']==1.5
    assert 'bbox' not in payload and 'landmarks' not in payload
    assert len([e for e in events if e['kind']=='face_presence'])>10


def test_brief_or_one_sided_smile_does_not_trigger():
    assert not cues(feed(FaceCueEngine(),face(),count=4))
    assert not cues(feed(FaceCueEngine(),face(mouthSmileRight=.1),count=30))


def test_neutral_release_and_global_cooldown():
    engine=FaceCueEngine()
    assert len(cues(feed(engine,face(),count=6)))==1
    feed(engine,face(.1),start=101.2,count=5)
    assert not cues(feed(engine,face(),start=102.2,count=8))
    feed(engine,face(.1),start=103.8,count=5)
    assert len(cues(feed(engine,face(),start=105,count=50)))==1


def test_multiface_and_quality_emit_unknown_not_cues():
    engine=FaceCueEngine()
    for i in range(20):
        events=engine.update(FaceObservation(100+i*.2,(face(),face()),dict(QUALITY)),now=100+i*.2)
        assert not cues(events)
        assert all(e['kind']=='visual_unknown' and e['payload']['track_id'] is None for e in events)
    bad=FaceSample(face().bbox,face().coefficients,{'usable':False,'reasons':['blur']})
    assert all(e['kind']=='visual_unknown' for e in feed(FaceCueEngine(),bad))


def test_no_face_requires_stability_and_renews_absence():
    events=feed(FaceCueEngine(),None,count=20)
    assert not cues(events)
    absent=[e for e in events if e['kind']=='face_presence']
    assert len(absent)>2 and all(e['payload']['present'] is False for e in absent)


@pytest.mark.parametrize('timestamp,now',[(100,102),(102,100),(float('nan'),100),(100,float('inf'))])
def test_bad_time_does_not_advance(timestamp,now):
    engine=FaceCueEngine()
    assert engine.update(FaceObservation(timestamp,(face(),),QUALITY),now=now)==[]
    assert engine.last_timestamp==float('-inf')


def test_gap_resets_track_and_smile_window():
    engine=FaceCueEngine()
    feed(engine,face(),count=3)
    old=engine.track_id
    events=feed(engine,face(),start=102,count=3)
    assert engine.track_id!=old and not cues(events)


def test_real_face_model_blank_frame_if_installed():
    from pathlib import Path
    model=Path('.runtime/models/face_landmarker.task')
    if not model.exists(): pytest.skip('Explicitly download official face model first')
    np=pytest.importorskip('numpy')
    pytest.importorskip('mediapipe')
    from pet_vision.face_detector import MediaPipeFaceDetector
    detector=MediaPipeFaceDetector(model)
    try:
        result=detector.detect(np.zeros((360,640,3),dtype=np.uint8),100)
        assert not result.faces and result.frame_quality['usable'] is False
    finally:
        detector.close()


def test_laugh_like_needs_open_mouth_and_cheek_cues_not_audio():
    sample=face(.8,jawOpen=.5,cheekSquintLeft=.4,cheekSquintRight=.4)
    result=cues(feed(FaceCueEngine(extended=True),sample,count=30))
    laugh=[e for e in result if e['payload']['cue_name']=='laugh_like']
    assert len(laugh)==1 and laugh[0]['payload']['stable_ms']>=1200
    assert laugh[0]['payload']['audible_evidence'] is False
    assert laugh[0]['payload']['provisional'] is True
    assert not any(e['payload']['cue_name']=='laugh_like' for e in cues(feed(FaceCueEngine(extended=True),face(.8,jawOpen=.8),count=20)))


def crying_pattern(**extra):
    return face(.1,browInnerUp=.8,mouthFrownLeft=.7,mouthFrownRight=.7,eyeSquintLeft=.5,eyeSquintRight=.5,**extra)


def test_possible_crying_is_sustained_provisional_pattern_not_tears():
    engine=FaceCueEngine(extended=True)
    assert not cues(feed(engine,crying_pattern(),count=12))
    result=cues(feed(engine,crying_pattern(),start=102.4,count=8))
    assert len(result)==1 and result[0]['payload']['cue_name']=='possible_crying'
    assert result[0]['payload']['stable_ms']>=2500
    assert result[0]['payload']['requires_context'] and not result[0]['payload']['tear_evidence']
    assert not cues(feed(FaceCueEngine(extended=True),face(.1,mouthFrownLeft=.8,mouthFrownRight=.8),count=30))


def test_playful_pattern_does_not_classify_ordinary_motion():
    engine=FaceCueEngine(extended=True)
    events=[]
    for i in range(30):
        x=.005*(i%5)
        neutral=FaceSample((.3+x,.2,.7+x,.8),face(.1).coefficients,dict(QUALITY))
        events+=feed(engine,neutral,start=100+i*.2,count=1)
    assert not cues(events)
    result=cues(feed(FaceCueEngine(extended=True),face(.1,mouthPucker=.8,browOuterUpLeft=.6,browOuterUpRight=.6),count=20))
    assert len(result)==1 and result[0]['payload']['cue_name']=='playful_activity'
    assert result[0]['payload']['provisional'] is True


def test_extended_patterns_disabled_by_default_and_multiface_blocked():
    assert not cues(feed(FaceCueEngine(),crying_pattern(),count=30))
    engine=FaceCueEngine(extended=True)
    for i in range(30):
        result=engine.update(FaceObservation(100+i*.2,(crying_pattern(),crying_pattern()),QUALITY),now=100+i*.2)
        assert not cues(result)


def test_extended_mode_cannot_send_to_production_cli():
    import subprocess,sys
    result=subprocess.run([sys.executable,'tools/run_pet_vision.py','--mode','face','--provider',
                           'pet_vision.ipc:leased_opencv_frames','--extended-face-cues','--send'],
                          capture_output=True,text=True,timeout=10)
    assert result.returncode==2 and 'observation-only' in result.stderr

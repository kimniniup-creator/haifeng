"""Observable face cues, not emotion probabilities or identity recognition."""
from dataclasses import dataclass
from math import dist, isfinite
from uuid import uuid4


@dataclass(frozen=True)
class FaceSample:
    bbox: tuple[float, float, float, float]  # transient association only; not sent
    coefficients: dict[str, float]
    quality: dict

    def valid(self):
        return (len(self.bbox)==4 and all(isfinite(v) for v in self.bbox)
                and self.bbox[0]<self.bbox[2] and self.bbox[1]<self.bbox[3]
                and all(isfinite(v) and 0<=v<=1 for v in self.coefficients.values()))

    @property
    def center(self):
        return ((self.bbox[0]+self.bbox[2])/2,(self.bbox[1]+self.bbox[3])/2)


@dataclass(frozen=True)
class FaceObservation:
    observed_at: float
    faces: tuple[FaceSample, ...]
    frame_quality: dict


class FaceCueEngine:
    """One producer, short-lived spatial track, no persisted biometric identity.

    Single-face quality gating precedes every cue. Insufficient evidence is
    unknown. All thresholds are heuristics requiring target-camera validation.
    """
    def __init__(self, *, session_id=None, confidence=.7, extended=False):
        self.session_id=session_id or str(uuid4())
        self.confidence=confidence
        self.extended=extended
        self.last_timestamp=float('-inf')
        self.max_age=.75
        self.track_id=None
        self.center=None
        self.track_since=None
        self.absent_since=None
        self.last_status=None
        self.last_status_at=float('-inf')
        self.candidates={}
        self.latched=set()
        self.release_since={}
        self.cooldowns={}

    def _reset_track(self):
        self.track_id=self.center=self.track_since=None
        self.candidates.clear()
        self.latched.clear()
        self.release_since.clear()

    def _event(self,kind,t,payload):
        return dict(schema_version=1,source='vision',session_id=self.session_id,
                    event_id=str(uuid4()),kind=kind,observed_at=t,ttl_seconds=1.5,
                    confidence=self.confidence,payload=payload)

    def _payload(self,faces,quality,**fields):
        return dict(track_id=self.track_id,face_count=faces,face_count_limit=2,
                    attribution='single_face' if faces==1 and self.track_id else 'ambiguous' if faces>1 else 'none',
                    quality=quality,confidence_basis='configured_detection_floor',**fields)

    def _status(self,kind,t,payload,key):
        if key!=self.last_status or t-self.last_status_at>=.75:
            self.last_status,self.last_status_at=key,t
            return [self._event(kind,t,payload)]
        return []

    def update(self,observation:FaceObservation,*,now):
        t=observation.observed_at
        if not isfinite(t) or not isfinite(now) or t<=self.last_timestamp or t>now+.05 or now-t>self.max_age:
            return []
        if t-self.last_timestamp>.4:
            self._reset_track()
            self.absent_since=None
        self.last_timestamp=t
        faces=observation.faces
        if observation.frame_quality.get('usable') is not True:
            self._reset_track()
            self.absent_since=None
            return self._status('visual_unknown',t,self._payload(len(faces),observation.frame_quality,
                                unknown_reason='frame_quality'),'frame_quality')
        if not faces:
            self._reset_track()
            if self.absent_since is None:
                self.absent_since=t
            if t-self.absent_since<.6:
                return self._status('visual_unknown',t,self._payload(0,observation.frame_quality,
                                    unknown_reason='no_face_pending'),'no_face_pending')
            return self._status('face_presence',t,self._payload(0,observation.frame_quality,
                                present=False,stable_ms=round((t-self.absent_since)*1000)),'absent')
        self.absent_since=None
        if len(faces)!=1:
            self._reset_track()
            return self._status('visual_unknown',t,self._payload(len(faces),{'usable':False,'reasons':['multiple_faces']},
                                unknown_reason='multiple_faces'),'multiple_faces')
        face=faces[0]
        if not face.valid() or face.quality.get('usable') is not True:
            self._reset_track()
            return self._status('visual_unknown',t,self._payload(1,face.quality,
                                unknown_reason='face_quality'),'face_quality')
        if self.center is None or dist(self.center,face.center)>.12:
            self._reset_track()
            self.track_id=str(uuid4())
            self.track_since=t
        self.center=face.center
        if t-self.track_since<.3:
            status=self._status('visual_unknown',t,self._payload(1,face.quality,
                                unknown_reason='track_stabilizing'),'track_stabilizing')
        else:
            status=self._status('face_presence',t,self._payload(1,face.quality,present=True,
                                stable_ms=round((t-self.track_since)*1000)),('visible',self.track_id))
        status.extend(self._cues(face,t))
        return status

    def _rule(self,name,face,t,*,active,released,duration,thresholds,keys,cooldown=12,provisional=False):
        if released:
            self.candidates.pop(name,None)
            self.release_since.setdefault(name,t)
            if t-self.release_since[name]>=.6:
                self.latched.discard(name)
            return []
        self.release_since.pop(name,None)
        if not active:
            self.candidates.pop(name,None)
            return []
        candidate=self.candidates.setdefault(name,[t,0])
        candidate[1]+=1
        if (name in self.latched or candidate[1]<4 or t-candidate[0]+1e-6<duration
                or t-self.cooldowns.get(name,float('-inf'))<cooldown):
            return []
        self.latched.add(name)
        self.cooldowns[name]=t
        payload=self._payload(1,face.quality,cue_name=name,stable_ms=round((t-candidate[0])*1000),
                              rule_basis={'version':'face-cues-v1','coefficients':{k:face.coefficients.get(k,0.) for k in keys},
                                          'thresholds':thresholds},
                              interpretation='visible_facial_cue',provisional=provisional)
        return [self._event('visual_cue',t,payload)]

    def _cues(self,face,t):
        left=face.coefficients.get('mouthSmileLeft')
        right=face.coefficients.get('mouthSmileRight')
        if left is None or right is None:
            self.candidates.clear()
            return []
        smile=self._rule('smile',face,t,active=min(left,right)>=.55,
                         released=max(left,right)<=.35,duration=.8,
                         thresholds={'mouthSmileLeft':.55,'mouthSmileRight':.55},
                         keys=('mouthSmileLeft','mouthSmileRight'))
        if not self.extended:
            return smile
        # Extended names remain observation-only until the response owner adds an
        # explicitly reviewed policy. They do not establish laughter or tears.
        c=face.coefficients
        def enough(keys):
            return all(k in c for k in keys)
        laugh_keys=('mouthSmileLeft','mouthSmileRight','jawOpen','cheekSquintLeft','cheekSquintRight')
        cry_keys=('browInnerUp','mouthFrownLeft','mouthFrownRight','eyeSquintLeft','eyeSquintRight')
        play_keys=('mouthPucker','browOuterUpLeft','browOuterUpRight')
        laugh_active=(enough(laugh_keys) and min(left,right)>=.65 and c['jawOpen']>=.35
                      and min(c['cheekSquintLeft'],c['cheekSquintRight'])>=.2)
        crying_active=(enough(cry_keys) and max(left,right)<=.2 and c['browInnerUp']>=.6
                       and min(c['mouthFrownLeft'],c['mouthFrownRight'])>=.45
                       and min(c['eyeSquintLeft'],c['eyeSquintRight'])>=.3)
        playful_active=(enough(play_keys) and max(left,right)<.55 and c['mouthPucker']>=.6
                        and min(c['browOuterUpLeft'],c['browOuterUpRight'])>=.35 and not crying_active)
        rules=(
            ('laugh_like',laugh_active,1.2,12,dict(mouthSmileLeft=.65,mouthSmileRight=.65,jawOpen=.35,
                                                cheekSquintLeft=.2,cheekSquintRight=.2),laugh_keys),
            ('possible_crying',crying_active,2.5,30,dict(browInnerUp=.6,mouthFrownLeft=.45,mouthFrownRight=.45,
                                                       eyeSquintLeft=.3,eyeSquintRight=.3,max_smile=.2),cry_keys),
            ('playful_activity',playful_active,1.2,15,dict(mouthPucker=.6,browOuterUpLeft=.35,
                                                       browOuterUpRight=.35,max_smile=.55),play_keys))
        extra=[]
        for name,active,duration,cooldown,thresholds,keys in rules:
            emitted=self._rule(name,face,t,active=active,released=not active,duration=duration,
                               thresholds=thresholds,keys=keys,cooldown=cooldown,provisional=True)
            for event in emitted:
                event['payload']['interpretation']='candidate_facial_pattern'
                event['payload']['requires_context']=True
                event['payload']['audible_evidence']=False
                event['payload']['tear_evidence']=False
            extra.extend(emitted)
        # Smiling and open-mouth smiling may both be observed; the backend must
        # not turn these into two responses. Default deployment remains smile-only.
        return smile+extra

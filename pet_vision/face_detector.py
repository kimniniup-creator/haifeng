"""Real local MediaPipe Face Landmarker adapter. No camera or cloud I/O."""
from dataclasses import dataclass
from math import asin,atan2,degrees
from pathlib import Path
from .face_cues import FaceSample,FaceObservation


@dataclass(frozen=True)
class QualityThresholds:
    min_face_pixels: int=80
    min_brightness: float=35.
    max_brightness: float=225.
    min_sharpness: float=25.
    max_yaw: float=35.
    max_pitch: float=30.


def image_quality(bgr,thresholds):
    import cv2
    if not bgr.size:
        return {'usable':False,'reasons':['empty_image']}
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    brightness=float(gray.mean())
    sharpness=float(cv2.Laplacian(gray,cv2.CV_64F).var())
    reasons=[]
    if not thresholds.min_brightness<=brightness<=thresholds.max_brightness:
        reasons.append('exposure')
    if sharpness<thresholds.min_sharpness:
        reasons.append('blur_or_low_texture')
    return dict(usable=not reasons,reasons=reasons,brightness=round(brightness,2),sharpness=round(sharpness,2))


class MediaPipeFaceDetector:
    def __init__(self,model_path,confidence=.7,quality_thresholds=None):
        import mediapipe as mp
        self.mp=mp
        self.thresholds=quality_thresholds or QualityThresholds()
        # Read bytes in Python: avoids native fopen failures for Unicode paths.
        self.landmarker=mp.tasks.vision.FaceLandmarker.create_from_options(
            mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_buffer=Path(model_path).read_bytes()),
                running_mode=mp.tasks.vision.RunningMode.IMAGE,num_faces=2,
                min_face_detection_confidence=confidence,min_face_presence_confidence=confidence,
                output_face_blendshapes=True,output_facial_transformation_matrixes=True))

    def detect(self,bgr_frame,observed_at):
        import numpy as np
        if bgr_frame.dtype!=np.uint8 or bgr_frame.ndim!=3 or bgr_frame.shape[2]!=3:
            raise ValueError('Expected HxWx3 uint8 BGR frame')
        frame_quality=image_quality(bgr_frame,self.thresholds)
        result=self.landmarker.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                                      data=np.ascontiguousarray(bgr_frame[:,:,::-1])))
        height,width=bgr_frame.shape[:2]
        faces=[]
        for i,points in enumerate(result.face_landmarks):
            xs,ys=[p.x for p in points],[p.y for p in points]
            bbox=(min(xs),min(ys),max(xs),max(ys))
            x1,y1,x2,y2=bbox
            crop=bgr_frame[max(0,int(y1*height)):min(height,int(y2*height)),
                           max(0,int(x1*width)):min(width,int(x2*width))]
            quality=image_quality(crop,self.thresholds)
            reasons=quality['reasons']
            face_pixels=min((x2-x1)*width,(y2-y1)*height)
            quality['face_pixels']=round(face_pixels,1)
            if face_pixels<self.thresholds.min_face_pixels:
                reasons.append('face_too_small')
            if min(x1,y1)<.01 or max(x2,y2)>.99:
                reasons.append('face_clipped')
            if i>=len(result.facial_transformation_matrixes):
                reasons.append('pose_unknown')
            else:
                rotation=np.asarray(result.facial_transformation_matrixes[i],dtype=float)[:3,:3]
                scale=np.linalg.norm(rotation,axis=0)
                if not np.isfinite(rotation).all() or (scale<1e-8).any():
                    reasons.append('pose_unknown')
                else:
                    rotation=rotation/scale
                    yaw=degrees(asin(float(np.clip(-rotation[2,0],-1,1))))
                    pitch=degrees(atan2(rotation[2,1],rotation[2,2]))
                    quality.update(yaw_degrees=round(yaw,1),pitch_degrees=round(pitch,1))
                    if abs(yaw)>self.thresholds.max_yaw or abs(pitch)>self.thresholds.max_pitch:
                        reasons.append('face_oblique')
            quality['usable']=not reasons
            coefficients={c.category_name:float(c.score) for c in result.face_blendshapes[i]} if i<len(result.face_blendshapes) else {}
            faces.append(FaceSample(bbox,coefficients,quality))
        return FaceObservation(observed_at,tuple(faces),frame_quality)

    def close(self):
        self.landmarker.close()

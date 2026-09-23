"""Read-only allowlisted Reachy REST audit. Raw responses stay in ignored .runtime."""
import json, urllib.request, urllib.error
from pathlib import Path
BASE='http://127.0.0.1:8000'
OUT=Path(__file__).resolve().parents[1]/'.runtime'
def request(method,path,body=None):
 req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'},method=method)
 try:
  with urllib.request.urlopen(req,timeout=8) as r: code,raw=r.status,r.read()
 except urllib.error.HTTPError as e: code,raw=e.code,e.read()
 try: value=json.loads(raw)
 except Exception: value=raw.decode(errors='replace')[:1000]
 return {'method':method,'path':path,'code':code,'response':value}
def main():
 paths=['/api/daemon/status','/api/daemon/robot-name','/api/daemon/hardware-id','/api/daemon/robot-app-lock-status','/api/motors/status','/api/state/present_head_pose','/api/state/present_body_yaw','/api/state/present_antenna_joint_positions','/api/state/full','/api/state/doa','/api/state/imu','/api/camera/specs','/api/media/status','/api/media/tracking/face','/api/media/sounds','/api/volume/current','/api/volume/microphone/current','/api/move/running','/api/kinematics/info','/api/kinematics/urdf','/api/apps/list-available/installed','/api/apps/list-available/local','/api/apps/current-app-status','/api/apps/startup-app','/api/audio/config/parameter/DOA_VALUE_RADIANS']
 results=[]
 for p in paths:
  try:r=request('GET',p)
  except Exception as e:r={'method':'GET','path':p,'error':str(e)}
  results.append(r);print(json.dumps(r,ensure_ascii=True)[:1600],flush=True)
 results.append(request('POST','/health-check'))
 OUT.mkdir(exist_ok=True);(OUT/'rest-audit.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
if __name__=='__main__':main()

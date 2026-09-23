"""Explicit bounded antenna motion audit; restores initial mode and antenna targets."""
import asyncio,json,time
from pathlib import Path
import websockets
from reachy_api_audit import request
results=[]
def req(m,p,b=None):
 r=request(m,p,b);results.append(r);print(json.dumps(r),flush=True)
 if r.get('code')!=200:raise RuntimeError(str(r))
 return r['response']
async def main():
 s=req('GET','/api/daemon/status');assert s['state']=='running' and not s['simulation_enabled']
 assert req('GET','/api/move/running')==[]
 orig=req('GET','/api/state/present_antenna_joint_positions');mode=req('GET','/api/motors/status')['mode']
 async with websockets.connect('ws://127.0.0.1:8000/api/move/ws/updates') as ws:
  try:
   req('POST','/api/motors/set_mode/enabled')
   target=[orig[0]+.05,orig[1]]
   move=req('POST','/api/move/goto',{'antennas':target,'duration':1})
   for i in range(2):results.append({'event':json.loads(await asyncio.wait_for(ws.recv(),4))})
   await asyncio.sleep(.7)
   req('GET','/api/state/present_antenna_joint_positions')
   move=req('POST','/api/move/goto',{'antennas':orig,'duration':2})
   await asyncio.sleep(.25);req('GET','/api/move/running');req('POST','/api/move/stop',move)
   for i in range(2):results.append({'event':json.loads(await asyncio.wait_for(ws.recv(),4))})
   req('POST','/api/move/goto',{'antennas':orig,'duration':1});await asyncio.sleep(1.3)
   req('POST','/api/move/set_target',{'target_antennas':orig})
   async with websockets.connect('ws://127.0.0.1:8000/api/move/ws/set_target') as w:await w.send(json.dumps({'target_antennas':orig}))
   req('GET','/api/state/present_antenna_joint_positions')
  finally:req('POST','/api/motors/set_mode/'+mode)
 for path in ['/api/state/ws/full','/ws/sdk']:
  try:
   async with websockets.connect('ws://127.0.0.1:8000'+path) as w:
    msg=await asyncio.wait_for(w.recv(),3);results.append({'ws':path,'sample':str(msg)[:1800]})
  except Exception as e:results.append({'ws':path,'error':repr(e)})
 req('GET','/api/move/running');req('GET','/api/daemon/status')
try:asyncio.run(main())
finally:Path('.runtime/motion-audit.json').write_text(json.dumps(results,indent=2))

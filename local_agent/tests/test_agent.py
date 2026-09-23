import asyncio
import io
import json
import time
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from agent_app.config import Config
from agent_app.contracts import Observation, JobRequest, Respond, tool_specs
from agent_app.storage import Store, uid, now
from agent_app.media import Media
from agent_app.service import Service
from agent_app.main import create_app

def jpeg(color='green'):
    buf=io.BytesIO();Image.new('RGB',(40,30),color).save(buf,format='JPEG');return buf.getvalue()

class FakeModels:
    delay = 0
    def __init__(self,cfg,store): self.store=store;self.seen=[]
    async def observe(self,path,question,job=None):
        await asyncio.sleep(self.delay)
        self.seen.append(Path(path).read_bytes())
        return {'summary':'一盆植物','visible_objects':['植物'],'readable_text':[],
            'uncertainties':[],'image_quality':'usable','answer':'我看到了植物。','needs_better_image':False}
    async def decide(self,messages,job=None,force_respond=False):
        await asyncio.sleep(self.delay)
        ctx=json.loads(messages[1]['content']);text=ctx['user_text']
        had_tool=any(m['role']=='tool' for m in messages)
        if '记住' in text and not had_tool and not force_respond:
            name='remember_event';args={'text':text,'evidence_ids':[ctx['context_data']['user_message_id']],'kind':'user_statement'}
        elif '历史' in text and not had_tool and not force_respond:
            name='search_memory';args={'query':'植物','limit':5}
        else:
            name='respond';args={'text':'我看到这盆植物了。','expression':'nod','delivery':'robot_and_text'}
        return {'role':'assistant','tool_calls':[{'id':uid('call'),'type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}
    async def close(self): pass

class FakeRobot:
    def __init__(self,cfg): self.played=0;self.moved=0;self.audio_active=False
    async def capabilities(self): return {'ready':True,'reachable':True,'missing_routes':[]}
    async def express(self,name): self.moved+=1;return {'status':'completed'}
    async def play(self,path): self.played+=1;return {'status':'accepted'}
    async def stop(self): return []
    async def close(self): pass

class FakeMedia(Media):
    def __init__(self,cfg,store): super().__init__(cfg,store);self.captures=0;self.tts_calls=0
    async def capture(self,sid): self.captures+=1;return self.register(jpeg(),sid)
    async def tts(self,text): self.tts_calls+=1;return self.cfg.data/'audio'/'fake.wav',0

@pytest.fixture
def client(tmp_path):
    cfg=Config(root=tmp_path,data=tmp_path/'data',token='test-secret',api_key='test',reachy_mode='real', auto_memory=True,
        allowed_hosts=('localhost','127.0.0.1','private'))
    app=create_app(cfg,FakeModels,FakeRobot,FakeMedia)
    with TestClient(app,headers={'Authorization':'Bearer test-secret'}) as c:
        yield c,app

def session(c): return c.post('/api/sessions').json()['session_id']

def wait(c,jid):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        row=c.get('/api/jobs/'+jid).json()
        if row['status'] in ('completed','failed','cancelled','interrupted'): return row
        time.sleep(.02)
    raise AssertionError('job timeout')

def submit(c,sid,kind='capture',text='看看这个',image_id=None,request_id=None):
    r=c.post('/api/jobs',json={'session_id':sid,'request_id':request_id or uid('req'),
        'kind':kind,'text':text,'image_id':image_id})
    assert r.status_code==202,r.text
    return r.json()['id']

def test_capture_to_observation_agent_robot_memory(client):
    c,app=client;sid=session(c);jid=submit(c,sid,text='记住这是今天买的植物')
    result=wait(c,jid)
    assert result['status']=='completed',result
    assert result['result']['observation']['content']['summary']=='一盆植物'
    assert result['result']['expression_result']['speech']['status']=='accepted'
    assert app.state.svc.robot.played==app.state.svc.robot.moved==1
    assert len(c.get('/api/memories').json()['memories'])==2
    assert c.get('/api/images/'+result['image_id']).headers['content-type']=='image/jpeg'

def test_job_trace_exposes_agent_record_and_robot_receipt(client):
    c, _ = client; sid = session(c); jid = submit(c, sid)
    result = wait(c, jid)
    trace = c.get('/api/jobs/'+jid+'/trace')
    assert trace.status_code == 200
    payload = trace.json()
    assert payload['job']['id'] == jid
    assert any(message['role'] == 'tool' for message in payload['messages'])
    assert payload['effect']['result']['text']['status'] == 'completed'
    assert payload['effect']['result']['motion']['status'] == 'completed'
    assert payload['effect']['result']['speech']['status'] == 'accepted'

def test_duplicate_request_does_not_capture_twice(client):
    c,app=client;sid=session(c);rid=uid('req')
    jid=submit(c,sid,request_id=rid);wait(c,jid)
    again=submit(c,sid,request_id=rid)
    assert jid==again and app.state.svc.media.captures==1 and app.state.svc.robot.played==1

def test_different_request_same_scene_is_new_share(client):
    c,app=client;sid=session(c)
    a=wait(c,submit(c,sid));b=wait(c,submit(c,sid))
    assert a['image_id']!=b['image_id'] and app.state.svc.media.captures==2

def test_conflicting_idempotency_key(client):
    c,_=client;sid=session(c);rid=uid('req');wait(c,submit(c,sid,request_id=rid))
    r=c.post('/api/jobs',json={'session_id':sid,'request_id':rid,'kind':'capture','text':'different'})
    assert r.status_code==409

def test_followup_uses_same_image_no_new_capture(client):
    c,app=client;sid=session(c);first=wait(c,submit(c,sid))
    next_=wait(c,submit(c,sid,kind='message',text='花盆是什么颜色',image_id=first['image_id']))
    assert next_['image_id']==first['image_id'] and app.state.svc.media.captures==1
    assert len(app.state.svc.models.seen)==2

def test_cross_session_image_rejected(client):
    c,_=client;s1=session(c);s2=session(c);result=wait(c,submit(c,s1))
    r=c.post('/api/jobs',json={'session_id':s2,'request_id':uid('req'),'kind':'image','image_id':result['image_id']})
    assert r.status_code==400

def test_upload_automatically_analyzed_after_submit(client):
    c,app=client;sid=session(c)
    r=c.post('/api/images',data={'session_id':sid},files={'image':('test.jpg',jpeg(),'image/jpeg')})
    iid=r.json()['image_id'];result=wait(c,submit(c,sid,kind='image',image_id=iid))
    assert result['status']=='completed' and app.state.svc.media.captures==0

def test_bad_jpeg_rejected(client):
    c,_=client;sid=session(c)
    r=c.post('/api/images',data={'session_id':sid},files={'image':('bad.jpg',b'garbage','image/jpeg')})
    assert r.status_code in (400,422)

def test_quiet_has_no_tts_or_motion(client):
    c,app=client;sid=session(c);c.patch('/api/sessions/'+sid+'/mode',json={'quiet':True})
    result=wait(c,submit(c,sid))
    assert result['status']=='completed' and app.state.svc.robot.played==0
    assert app.state.svc.media.tts_calls==0 and app.state.svc.robot.moved==0

def test_cancel_during_model_prevents_expression(client):
    c,app=client;sid=session(c);app.state.svc.models.delay=.3
    jid=submit(c,sid);time.sleep(.04);c.post('/api/jobs/'+jid+'/cancel')
    assert wait(c,jid)['status']=='cancelled'
    assert app.state.svc.robot.played==0

def test_memory_cross_session_retrieval_edit_delete(client):
    c,_=client;sid=session(c);wait(c,submit(c,sid,text='记住我的植物'))
    second=session(c);assert wait(c,submit(c,second,kind='message',text='查历史'))['status']=='completed'
    found=c.get('/api/memories?q=植物').json()['memories'];assert found
    old=found[0]['id'];new=c.patch('/api/memories/'+old,json={'text':'这是朋友的植物'}).json()['memory_id']
    assert old not in [m['id'] for m in c.get('/api/memories').json()['memories']]
    c.delete('/api/memories/'+new)
    assert new not in [m['id'] for m in c.get('/api/memories').json()['memories']]

def test_invalid_evidence_rejected(client):
    _,app=client;s=app.state.svc.store;sid=s.session()
    with pytest.raises(ValueError): s.memory('无来源事实',['missing'],'user_statement',sid)

def test_auth_and_origin(client):
    c,_=client
    assert c.get('/api/health',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert c.post('/api/sessions',headers={'Origin':'https://unrelated.example'}).status_code==403

def test_private_network_host_is_allowed_but_public_host_is_rejected(client):
    c,_=client
    assert c.get('/api/health',headers={'Host':'192.168.10.45:8765'}).status_code==200
    assert c.get('/api/health',headers={'Host':'agent.example.com:8765'}).status_code==403

def test_recovery_does_not_replay_effect(tmp_path):
    s=Store(tmp_path/'db');sid=s.session()
    s.execute('INSERT INTO jobs(id,session_id,request_id,kind,text,status,created) VALUES(?,?,?,?,?,?,?)',
        ('job',sid,'req','message','hi','expressing',now()))
    assert s.claim_effect('job');s.recover()
    assert s.job('job')['status']=='interrupted'
    assert s.one('SELECT status FROM effects WHERE job_id=?',('job',))['status']=='unknown'
    assert not s.claim_effect('job');s.close()

def test_persistent_memory_survives_restart(tmp_path):
    s=Store(tmp_path/'db');sid=s.session();mid=s.message(sid,None,'user',{'text':'植物'})
    memory=s.memory('植物',[mid],'user_statement',sid);s.close();s=Store(tmp_path/'db')
    assert s.search('植物')[0]['id']==memory;s.close()

def test_strict_tool_schema():
    for spec in tool_specs():
        schema=spec['function']['parameters']
        assert schema['additionalProperties'] is False
        assert set(schema['required'])==set(schema['properties'])

def test_queue_limit(client):
    c,app=client;sid=session(c);app.state.svc.models.delay=.2
    submit(c,sid)
    for _ in range(3): submit(c,sid)
    r=c.post('/api/jobs',json={'session_id':sid,'request_id':uid('req'),'kind':'capture'})
    assert r.status_code==429

def test_robot_offline_keeps_text_and_reports_failure(client):
    c,app=client;sid=session(c)
    async def offline(): return {'ready':False,'reachable':False}
    app.state.svc.robot.capabilities=offline
    result=wait(c,submit(c,sid))
    assert result['status']=='completed'
    assert result['result']['expression_result']['text']['status']=='completed'
    assert result['result']['expression_result']['speech']['status']=='failed'
    assert app.state.svc.robot.played==0

def test_motion_failure_does_not_repeat_speech(client):
    c,app=client;sid=session(c)
    async def failed_motion(name): raise RuntimeError('move unavailable')
    app.state.svc.robot.express=failed_motion
    result=wait(c,submit(c,sid))
    assert result['result']['expression_result']['motion']['status']=='unknown'
    assert result['result']['expression_result']['speech']['status']=='accepted'
    assert app.state.svc.robot.played==1

def test_invalid_tool_parameters_never_move(client):
    c,app=client;sid=session(c)
    async def bad_decision(*args,**kwargs):
        return {'role':'assistant','tool_calls':[{'id':uid('call'),'type':'function',
            'function':{'name':'respond','arguments':json.dumps({'text':'hi','expression':'spin_unbounded','delivery':'robot_and_text'})}}]}
    app.state.svc.models.decide=bad_decision
    result=wait(c,submit(c,sid))
    assert result['status']=='failed' and app.state.svc.robot.moved==0 and app.state.svc.robot.played==0

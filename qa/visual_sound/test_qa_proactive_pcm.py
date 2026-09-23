import asyncio
import numpy as np
import pytest
import test_proactive_audio as original_tests

def rig():
    case=original_tests.ProactiveTests();case.setUp();return case

def submit(case):
    body=case.body();body['ttl_ms']=1500
    result=case.client.post('/api/proactive-sound',json=body,headers={'Authorization':'Bearer test-only'})
    assert result.status_code==200 and result.json()['accepted']
    return body

def test_http_to_pcm_and_complete_preserves_real_final_identity():
    c=rig();c.pet.gate.final=True;c.pet.gate.answered=True;c.pet.last_final_at=90
    before=c.pet.gate.identity()
    submit(c); nonzero=False
    for _ in range(70):
        c.pet.last_capture=c.now;c.p.heartbeat(c.lease['connection_id'])
        out=np.zeros((320,2),dtype=np.float32);c.pet.gate.render(out)
        nonzero|=bool(np.any(out));c.now+=.02
        if c.pet.gate.pending is None:break
    assert nonzero and c.pet.gate.pending is None
    receipts=[]
    while not c.pet.gate.events.empty():receipts.append(c.pet.gate.events.get_nowait())
    assert [r['status'] for r in receipts]==['queued','started','completed']
    assert receipts[-1]['reason']=='last_buffer_submitted'
    assert c.pet.gate.identity()==before and c.pet.gate.final and c.pet.gate.answered

@pytest.mark.parametrize('boundary',['lease','send_failure','speech','deadline'])
def test_next_pcm_block_is_silent_after_invalidation(boundary):
    c=rig();submit(c)
    out=np.zeros((320,2));c.pet.gate.render(out);assert np.any(out)
    if boundary=='lease': c.now+=1.6;c.pet.last_capture=c.now
    elif boundary=='speech': c.pet.last_activity=c.now
    elif boundary=='deadline':
        deadline=c.pet.gate.pending[3]
        c.now=deadline-.1;c.p.heartbeat(c.lease['connection_id'])
        c.now=deadline;c.pet.last_capture=c.now
    else:
        class Socket:
            async def send_json(self,event):raise ConnectionError('fake')
            async def close(self,code):pass
        socket=Socket();c.pet.proactive_clients[socket]=c.lease['connection_id']
        asyncio.run(c.pet.emit(c.pet.gate.events.get_nowait()))
    out.fill(1);c.pet.gate.render(out)
    assert not np.any(out),boundary
    assert c.pet.gate.pending is None

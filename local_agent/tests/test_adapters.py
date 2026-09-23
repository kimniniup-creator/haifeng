import asyncio
import json
import sys
import io
from pathlib import Path
import httpx
import pytest
from openai import AsyncOpenAI
from PIL import Image
from agent_app.config import Config
from agent_app.storage import Store
from agent_app.models import Models
from agent_app.robot import Robot
from agent_app.media import run_process

@pytest.mark.parametrize('response_format', ['json_schema', 'json_object'])
def test_real_openai_adapter_request_and_strict_parse(tmp_path, response_format):
    async def check():
        cfg=Config(root=tmp_path,data=tmp_path/'data',api_key='unit-test', response_format=response_format)
        cfg.prepare();store=Store(cfg.data/'agent.db');model=Models(cfg,store)
        image=tmp_path/'sample.jpg';Image.new('RGB',(16,16),'red').save(image)
        observed=[]
        def handler(request):
            body=json.loads(request.content);observed.append(body)
            assert body['response_format']['type']==response_format
            if response_format == 'json_schema':
                assert body['response_format']['json_schema']['strict'] is True
            assert body['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
            content={'summary':'红色画面','visible_objects':[],'readable_text':[],
                'uncertainties':[],'image_quality':'usable','answer':'红色。','needs_better_image':False}
            return httpx.Response(200,json={'id':'test','object':'chat.completion','created':1,'model':'gpt-4o-mini',
                'choices':[{'index':0,'message':{'role':'assistant','content':json.dumps(content)},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}})
        await model.client.close()
        model.client=AsyncOpenAI(api_key='test',http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        result=await model.observe(image,'什么颜色')
        assert result['answer']=='红色。' and len(observed)==1
        assert store.one('SELECT count(*) AS n FROM model_calls')['n']==1
        await model.close();store.close()
    asyncio.run(check())

def test_robot_upload_play_accepted_and_stop(tmp_path):
    async def check():
        robot=Robot(Config());await robot.http.aclose();calls=[]
        def handler(request):
            calls.append(request.url.path)
            if request.url.path.endswith('/sounds/upload'):
                assert b'file' in request.content
                return httpx.Response(200,json={'path':'/robot/tmp/speech.wav'})
            if request.url.path.endswith('/play_sound'):
                assert json.loads(request.content)=={'file':'/robot/tmp/speech.wav'}
            return httpx.Response(200,json={'status':'ok'})
        robot.http=httpx.AsyncClient(base_url='http://robot',transport=httpx.MockTransport(handler))
        audio=tmp_path/'speech.wav';audio.write_bytes(b'test-fixture')
        result=await robot.play(audio)
        assert result['status']=='accepted' and result['status']!='completed'
        assert (await robot.stop())[0]['status']=='accepted'
        assert calls==['/api/media/acquire','/api/media/sounds/upload','/api/media/play_sound','/api/media/stop_sound']
        await robot.close()
    asyncio.run(check())

def test_subprocess_timeout_reaps_child():
    async def check():
        with pytest.raises(TimeoutError):
            await run_process(sys.executable,'-c','import time;time.sleep(20)',timeout=.1)
        out=await run_process(sys.executable,'-c','print("next-call-ok")',timeout=2)
        assert b'next-call-ok' in out
    asyncio.run(check())

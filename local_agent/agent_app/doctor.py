import argparse
import asyncio
import json
from pathlib import Path
from filelock import FileLock
from .config import Config
from .storage import Store
from .media import Media
from .models import Models
from .robot import Robot

async def run(args):
    cfg = Config()
    cfg.prepare()
    with FileLock(str(cfg.data/'agent.lock'), timeout=0):
        store = Store(cfg.data/'agent.db')
        media, model, robot = Media(cfg,store), Models(cfg,store), Robot(cfg)
        try:
            if args.robot:
                result = await robot.capabilities()
                print(json.dumps(result,ensure_ascii=False,indent=2))
                if not result.get('ready') or result.get('missing_routes'):
                    raise RuntimeError('ROBOT_CAPABILITIES_NOT_READY')
            if args.capture:
                sid = store.session()
                iid = await media.capture(sid)
                print(json.dumps(store.one('SELECT * FROM images WHERE id=?',(iid,)),ensure_ascii=False,indent=2))
            if args.models:
                if not args.image:
                    raise RuntimeError('--models requires --image PATH')
                # Same validation path as the application; malformed file never reaches API.
                sid = store.session()
                iid = media.register(Path(args.image).read_bytes(),sid)
                image = store.one('SELECT * FROM images WHERE id=?',(iid,))
                result = await model.observe(image['path'],'描述图中的主要物体')
                print(json.dumps({'vision_structured':result},ensure_ascii=False,indent=2))
                echo = {'type':'function','function':{'name':'echo','description':'Return supplied text unchanged.',
                    'strict':True,'parameters':{'type':'object','properties':{'text':{'type':'string'}},
                    'required':['text'],'additionalProperties':False}}}
                messages = [{'role':'user','content':'Call echo with text=ok, then report its result.'}]
                first = await model.client.chat.completions.create(model=cfg.agent_model,messages=messages,
                    tools=[echo],tool_choice={'type':'function','function':{'name':'echo'}},parallel_tool_calls=False)
                message = first.choices[0].message
                calls = message.tool_calls or []
                if len(calls)!=1 or calls[0].function.name!='echo':
                    raise RuntimeError('TOOL_CALL_PROBE_FAILED')
                payload = json.loads(calls[0].function.arguments)
                if payload.get('text')!='ok':
                    raise RuntimeError('TOOL_ARGUMENT_PROBE_FAILED')
                messages.append(message.model_dump(exclude_none=True))
                messages.append({'role':'tool','tool_call_id':calls[0].id,'content':json.dumps(payload)})
                final = await model.client.chat.completions.create(model=cfg.agent_model,messages=messages)
                if not final.choices[0].message.content:
                    raise RuntimeError('TOOL_RESULT_PROBE_FAILED')
                print('PASS: image input + structured output + tool call/result round trip')
            if args.tts or args.express:
                path, seconds = await media.tts('你好，我已经准备好和你一起看这个世界了。')
                print(json.dumps({'wav':str(path),'seconds':seconds},ensure_ascii=False))
                if args.express:
                    if cfg.reachy_mode!='real':
                        raise RuntimeError('Set REACHY_MODE=real for real expression test')
                    print(json.dumps(await robot.express('nod'),ensure_ascii=False))
                    print(json.dumps(await robot.play(path),ensure_ascii=False))
                    await asyncio.sleep(seconds+0.3)
                    robot.audio_active=False
                    print('请现场确认：Reachy点头并从其扬声器发声。HTTP accepted不等于已验证发声。')
        finally:
            await robot.stop()
            await model.close()
            await robot.close()
            store.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models',action='store_true')
    parser.add_argument('--image')
    parser.add_argument('--robot',action='store_true')
    parser.add_argument('--capture',action='store_true')
    parser.add_argument('--tts',action='store_true')
    parser.add_argument('--express',action='store_true')
    args=parser.parse_args()
    if not any((args.models,args.robot,args.capture,args.tts,args.express)):
        parser.error('Choose --models --image PATH, --robot, --capture, --tts or --express')
    asyncio.run(run(args))

if __name__=='__main__':
    main()

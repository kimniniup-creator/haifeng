import asyncio
import json
import sqlite3
from .contracts import TOOL_MODELS, Respond
from .models import AGENT_PROMPT
from .robot import EMOTION_TRAJECTORIES
from .storage import uid, now, dump

class Service:
    def __init__(self, cfg, store, media, models, robot):
        self.cfg, self.store, self.media = cfg, store, media
        self.models, self.robot = models, robot
        self.wakeup = asyncio.Event()
        self.runner = None
        self.active_task = None
        self.active_id = None
        self.state_lock = asyncio.Lock()

    async def start(self):
        self.store.recover()
        self.runner = asyncio.create_task(self.worker())
        self.wakeup.set()

    async def close(self):
        if self.runner:
            self.runner.cancel()
        if self.active_task:
            self.active_task.cancel()
        await asyncio.gather(*(t for t in (self.runner,self.active_task) if t), return_exceptions=True)
        await self.robot.stop()
        await self.models.close()
        await self.robot.close()

    def submit(self, request):
        sid = request.session_id
        if not self.store.one('SELECT id FROM sessions WHERE id=?', (sid,)):
            raise ValueError('SESSION_NOT_FOUND')
        existing = self.store.one('SELECT id,result FROM jobs WHERE session_id=? AND request_id=?', (sid,request.request_id))
        if existing:
            if json.loads(existing['result']).get('submitted') != request.model_dump():
                raise ValueError('IDEMPOTENCY_CONFLICT')
            return self.store.job(existing['id'])
        pending = self.store.one("SELECT count(*) AS n FROM jobs WHERE status='queued'")['n']
        if pending >= self.cfg.max_pending:
            raise ValueError('QUEUE_FULL')
        if request.kind == 'image' and not request.image_id:
            raise ValueError('IMAGE_REQUIRED')
        if request.image_id and not self.store.one('SELECT id FROM images WHERE id=? AND session_id=?', (request.image_id,sid)):
            raise ValueError('IMAGE_NOT_IN_SESSION')
        jid = uid('job')
        self.store.execute('INSERT INTO jobs(id,session_id,request_id,kind,text,image_id,status,result,created) VALUES(?,?,?,?,?,?,?,?,?)',
            (jid,sid,request.request_id,request.kind,request.text,request.image_id,'queued',dump({'submitted':request.model_dump()}),now()))
        self.wakeup.set()
        return self.store.job(jid)

    async def cancel(self, jid):
        row = self.store.job(jid)
        if not row:
            raise ValueError('JOB_NOT_FOUND')
        if row['status'] in ('completed','failed','cancelled','interrupted'):
            return {'status':row['status']}
        self.store.update_job(jid,'cancelled')
        reports = []
        if self.active_id == jid and self.active_task:
            self.active_task.cancel()
            await asyncio.gather(self.active_task, return_exceptions=True)
            reports = await self.robot.stop()
        return {'status':'cancelled','stop_reports':reports}

    async def quiet(self, sid, value):
        self.store.set_quiet(sid, value)
        if value and self.active_id:
            row = self.store.job(self.active_id)
            if row['session_id'] == sid:
                # Immediate stop; cancelled generation cannot restart speech.
                await self.cancel(self.active_id)
        return {'quiet':value}

    async def worker(self):
        try:
            while True:
                self.wakeup.clear()
                row = self.store.one("SELECT id FROM jobs WHERE status='queued' ORDER BY created LIMIT 1")
                if not row:
                    await self.wakeup.wait()
                    continue
                self.active_id = row['id']
                self.active_task = asyncio.create_task(self.process(row['id']))
                try:
                    await self.active_task
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling():
                        raise
                finally:
                    self.active_id = None
                    self.active_task = None
        except asyncio.CancelledError:
            return

    def check(self, jid):
        if self.store.job(jid)['status'] == 'cancelled':
            raise asyncio.CancelledError()

    async def observe(self, iid, question, jid):
        image = self.store.one('SELECT * FROM images WHERE id=?', (iid,))
        if not image:
            raise ValueError('IMAGE_NOT_FOUND')
        content = await self.models.observe(image['path'], question, jid)
        self.check(jid)
        oid = uid('obs')
        self.store.execute('INSERT INTO observations VALUES(?,?,?,?)', (oid,iid,dump(content),now()))
        return {'observation_id':oid,'image_id':iid,'received_at':image['created'],'content':content}

    async def process(self, jid):
        try:
            async with asyncio.timeout(self.cfg.turn_timeout):
                await self._process(jid)
        except asyncio.CancelledError:
            self.store.update_job(jid,'cancelled')
            effect = self.store.one('SELECT status FROM effects WHERE job_id=?', (jid,))
            if effect and effect['status']=='running':
                self.store.effect(jid,'unknown',{'reason':'cancelled during expression'})
            await self.robot.stop()
            raise
        except Exception as e:
            self.store.update_job(jid,'failed',error=type(e).__name__+': '+str(e)[:400])
            effect = self.store.one('SELECT status FROM effects WHERE job_id=?', (jid,))
            if effect and effect['status']=='running':
                self.store.effect(jid,'unknown',{'reason':'interrupted expression'})
            await self.robot.stop()

    async def _process(self, jid):
        row = self.store.job(jid)
        sid, iid, text = row['session_id'], row['image_id'], row['text']
        user_mid = self.store.message(sid,jid,'user',{'text':text,'kind':row['kind'],'image_id':iid})
        self.store.update_job(jid,'preparing',user_message_id=user_mid)
        if row['kind']=='capture':
            self.store.update_job(jid,'capturing')
            iid = await self.media.capture(sid)
            self.check(jid)
            self.store.execute('UPDATE jobs SET image_id=? WHERE id=?',(iid,jid))
            self.store.execute('UPDATE messages SET content=? WHERE id=?', (dump({'text':text,'kind':'capture','image_id':iid}),user_mid))
        if not iid and row['kind']=='message':
            prior = self.store.one("SELECT image_id FROM jobs WHERE session_id=? AND id!=? AND image_id IS NOT NULL AND status='completed' ORDER BY created DESC LIMIT 1",(sid,jid))
            iid = prior['image_id'] if prior else None
            if iid:
                self.store.execute('UPDATE jobs SET image_id=? WHERE id=?',(iid,jid))
        observation = None
        if iid:
            self.store.update_job(jid,'analyzing',image_id=iid)
            # Every image question sees the original, including follow-ups.
            observation = await self.observe(iid,text or '看看我主动分享的画面',jid)
            self.store.update_job(jid,'deciding',observation=observation)
            if self.cfg.auto_memory and row['kind'] in ('capture','image'):
                summary = observation['content']['summary']
                mid = self.store.memory('用户主动分享的画面：'+summary,
                    [observation['observation_id']], 'shared_observation',sid)
                self.store.update_job(jid,'deciding',auto_memory_id=mid)
        history = self.store.all("SELECT id,role,content FROM messages WHERE session_id=? AND job_id!=? AND role IN ('user','assistant') ORDER BY created DESC LIMIT 16",(sid,jid))
        history.reverse()
        memories = self.store.search(text,5)
        state = {'quiet':self.store.quiet(sid),'robot_mode':self.cfg.reachy_mode,
            'user_message_id':user_mid,'image_id':iid,'observation':observation,
            'history':history,'relevant_memories':memories}
        messages = [{'role':'system','content':AGENT_PROMPT},
                    {'role':'user','content':dump({'user_text':text,'context_data':state})}]
        self.store.update_job(jid,'deciding')
        inspect_count = 0
        for step in range(self.cfg.max_steps):
            self.check(jid)
            message = await self.models.decide(messages,jid,force_respond=step==self.cfg.max_steps-1)
            self.check(jid)
            messages.append(message)
            calls = message.get('tool_calls') or []
            if not calls:
                # Ask the same agent to choose delivery explicitly, no hidden TTS.
                messages.append({'role':'user','content':'请使用respond工具提交最终回应，遵守quiet状态。'})
                continue
            for call in calls:
                self.check(jid)
                name = call.get('function',{}).get('name')
                try:
                    if name not in TOOL_MODELS:
                        raise ValueError('UNKNOWN_TOOL')
                    args = TOOL_MODELS[name][0].model_validate_json(call['function']['arguments'])
                    if name=='inspect_image':
                        inspect_count += 1
                        if inspect_count > 2:
                            raise ValueError('INSPECT_LIMIT')
                        if not self.store.one('SELECT id FROM images WHERE id=? AND session_id=?',(args.image_id,sid)):
                            raise ValueError('IMAGE_NOT_IN_SESSION')
                        result = await self.observe(args.image_id,args.question,jid)
                    elif name=='search_memory':
                        result = {'memories':self.store.search(args.query,args.limit)}
                    elif name=='remember_event':
                        mid = self.store.memory(args.text,args.evidence_ids,args.kind,sid)
                        result = {'status':'completed','memory_id':mid}
                    elif name=='set_quiet_mode':
                        self.store.set_quiet(sid,args.enabled)
                        result = {'quiet':args.enabled}
                    else:
                        result = await self.respond(jid,args)
                    self.store.message(sid,jid,'tool',{'tool_call_id':call['id'],'name':name,'args':args.model_dump(),'result':result})
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':dump(result)})
                    if name=='respond':
                        self.store.update_job(jid,'completed',expression_result=result)
                        return
                except Exception as e:
                    result = {'status':'failed','error':type(e).__name__+': '+str(e)[:300]}
                    self.store.message(sid,jid,'tool',{'tool_call_id':call.get('id'),'name':name,'result':result})
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':dump(result)})
        raise RuntimeError('AGENT_STEP_LIMIT: no completed respond tool')

    async def respond(self, jid, args: Respond):
        self.check(jid)
        if not args.text.strip() or len(args.text)>160:
            raise ValueError('RESPONSE_LENGTH_MUST_BE_1_TO_160')
        if not self.store.claim_effect(jid):
            existing = self.store.one('SELECT * FROM effects WHERE job_id=?',(jid,))
            return {'status':'duplicate_blocked','previous':existing}
        row = self.store.job(jid)
        sid = row['session_id']
        observation = row['result'].get('observation', {}).get('content', {})
        expression = args.expression
        if row['kind'] in ('capture', 'image'):
            expression = observation.get('response_emotion', 'none')
            if observation.get('image_quality') not in ('usable', 'limited') or observation.get('needs_better_image') or not observation.get('emotion_evidence', '').strip():
                expression = 'none'
        self.store.message(sid,jid,'assistant',{'text':args.text})
        result = {'selected_emotion': expression,
                  'emotion_evidence': observation.get('emotion_evidence', ''),
                  'mapped_activity': {'type': 'head_gesture', 'segments_degrees': EMOTION_TRAJECTORIES.get(expression, [])},
                  'mapping_version': 'upstream-b078189',
                  'text':{'status':'completed','text':args.text},
                  'motion':{'status':'suppressed'},'speech':{'status':'suppressed'}}
        self.store.update_job(jid,'expressing',reply=args.text,expression_result=result)
        if args.delivery=='text_only' or self.store.quiet(sid) or self.cfg.reachy_mode=='text_only':
            result['mode']='text_only'
            self.store.effect(jid,'completed',result)
            return result
        caps = await self.robot.capabilities()
        self.check(jid)
        if not caps.get('ready'):
            result['motion']={'status':'failed','error':'ROBOT_NOT_READY'}
            result['speech']={'status':'failed','error':'ROBOT_NOT_READY'}
            self.store.effect(jid,'partial',result)
            return result
        audio = None
        if not self.cfg.speech_enabled:
            result['speech']={'status':'suppressed','detail':'ROBOT_SPEECH_DISABLED'}
        else:
            try:
                audio, seconds = await self.media.tts(args.text)
            except Exception as e:
                result['speech']={'status':'failed','error':str(e)[:250]}
        self.check(jid)
        try:
            result['motion'] = await self.robot.express(expression)
        except Exception as e:
            result['motion']={'status':'unknown','error':type(e).__name__+': '+str(e)[:200]}
        self.check(jid)
        if audio and not self.store.quiet(sid):
            try:
                result['speech'] = await self.robot.play(audio)
                self.store.update_job(jid,'expressing',expression_result=result)
                # Serialize speech with next turn, but do not call this verified completion.
                await asyncio.sleep(seconds + 0.3)
                result['speech']['estimated_duration_seconds']=round(seconds,2)
                self.robot.audio_active=False
            except Exception as e:
                result['speech']={'status':'unknown','error':type(e).__name__+': '+str(e)[:200]}
                await self.robot.stop()
        status = 'partial' if any(v.get('status') in ('failed','unknown') for v in result.values() if isinstance(v,dict)) else 'completed'
        self.store.effect(jid,status,result)
        return result

import asyncio
import unittest
import numpy as np
from fastapi.testclient import TestClient
from pet_companion import Companion, create_app
from proactive_audio import ProactiveAudio


class ProactiveTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.pet = Companion('unused', proactive_token='test-only')
        self.pet.gate.clock = lambda:self.now
        self.pet.gate.started_at = 90.
        self.pet.last_capture = 100.
        self.pet.last_activity = 90.
        self.pet.state['phase'] = 'listening'
        self.p = ProactiveAudio(self.pet, 'test-only', lambda:self.now, lambda:self.now+1000)
        self.pet.proactive = self.p
        self.lease = self.p.connect()
        self.client = TestClient(create_app(self.pet))

    def body(self, **kw):
        return dict(event_id='e1', connection_id=self.lease['connection_id'],
                    session_id=self.pet.gate.session_id, expected_epoch=self.pet.gate.epoch,
                    event_timestamp=self.now+1000, ttl_ms=2000, semantic_id='happy', **kw)

    def test_visual_accepted_without_fabricated_final(self):
        epoch=self.pet.gate.epoch
        r=self.p.submit(self.body())
        self.assertEqual(epoch,self.pet.gate.epoch)
        self.assertFalse(self.pet.gate.answered)
        self.assertTrue(r['accepted']); self.assertFalse(self.pet.gate.final)
        self.assertEqual(r['response_id'],'visual:e1')
        out=np.empty((320,2)); self.pet.gate.render(out)
        self.assertTrue(np.any(out))

    def test_token_default_disabled_and_wrong_rejected(self):
        for token in ('','wrong'):
            r=self.client.post('/api/proactive-sound',json=self.body(),headers={'Authorization':'Bearer '+token})
            self.assertEqual(r.status_code,403)
        self.p.token=''
        self.assertFalse(self.p.authorized('Bearer '))

    def test_authenticated_http(self):
        r=self.client.post('/api/proactive-sound',json=self.body(),headers={'Authorization':'Bearer test-only'})
        self.assertTrue(r.json()['accepted'])

    def test_busy_event_is_not_replayed(self):
        b=self.body();self.pet.state['phase']='hearing'
        self.assertEqual(self.p.submit(b)['reason'],'user_busy')
        self.pet.state['phase']='listening'
        self.assertEqual(self.p.submit(b)['reason'],'duplicate')

    def test_new_speech_or_stop_cancels(self):
        self.p.submit(self.body()); self.pet.interrupt('speech_started')
        out=np.ones((320,2));self.pet.gate.render(out)
        self.assertFalse(np.any(out))

    def test_pre_vad_activity_stops_next_callback(self):
        self.p.submit(self.body()); self.pet.last_activity=self.now
        out=np.ones((320,2)); self.pet.gate.render(out)
        self.assertFalse(np.any(out))

    def test_disconnect_cancels_and_old_connection_rejected(self):
        b=self.body();self.p.submit(b);self.p.disconnect(b['connection_id'])
        self.assertIsNone(self.pet.gate.pending)
        self.assertEqual(self.p.submit(b)['reason'],'disconnected')

    def test_heartbeat_timeout_stops_callback(self):
        self.p.submit(self.body());self.now+=1.6;self.pet.last_capture=self.now
        out=np.ones((320,2));self.pet.gate.render(out)
        self.assertFalse(np.any(out)); self.assertFalse(self.p.heartbeat(self.lease['connection_id']))

    def test_before_reconnect_event_rejected(self):
        b=self.body();self.now+=.1;self.lease=self.p.connect();b['connection_id']=self.lease['connection_id']
        self.assertEqual(self.p.submit(b)['reason'],'before_connection')

    def test_stale_epoch_and_session(self):
        for key,value in [('expected_epoch',-1),('session_id','old')]:
            b=self.body();b[key]=value
            self.assertEqual(self.p.submit(b)['reason'],'stale_turn')

    def test_cooldown(self):
        self.p.submit(self.body());self.pet.gate.pending=None
        self.now+=2;self.pet.last_capture=self.now;self.lease=self.p.connect()
        b=self.body();b['event_id']='e2'
        self.assertEqual(self.p.submit(b)['reason'],'cooldown')

    def test_invalid_or_expired_times(self):
        for key,value in [('ttl_ms',2001),('ttl_ms',float('nan')),('event_timestamp',float('inf'))]:
            b=self.body();b[key]=value
            self.assertEqual(self.p.submit(b)['reason'],'invalid_timing')
        b=self.body();b['event_timestamp']+=1
        self.assertEqual(self.p.submit(b)['reason'],'expired_or_future')
        b=self.body();b['ttl_ms']=100
        self.assertEqual(self.p.submit(b)['reason'],'insufficient_ttl')

    def test_user_voice_final_has_priority(self):
        self.pet.gate.final=True;self.pet.last_final_at=self.now
        self.assertEqual(self.p.submit(self.body())['reason'],'voice_priority')

    def test_muted_or_no_capture_rejected(self):
        self.pet.gate.muted=True
        self.assertEqual(self.p.submit(self.body())['reason'],'muted')
        self.pet.gate.muted=False;self.pet.last_capture=90
        b=self.body();b['event_id']='e2'
        self.assertEqual(self.p.submit(b)['reason'],'not_quiet')

    def test_finished_voice_does_not_block_forever(self):
        self.pet.gate.final=True; self.pet.gate.answered=True; self.pet.last_final_at=90
        self.assertTrue(self.p.submit(self.body())['accepted'])
        self.assertTrue(self.pet.gate.final); self.assertTrue(self.pet.gate.answered)

    def test_failed_receipt_disconnects_and_cancels(self):
        class Socket:
            async def send_json(self, event): raise ConnectionError()
            async def close(self, code): pass
        ws=Socket();self.pet.proactive_clients[ws]=self.lease['connection_id']
        self.p.submit(self.body())
        event=self.pet.gate.events.get_nowait()
        asyncio.run(self.pet.emit(event))
        self.assertIsNone(self.p.connection);self.assertIsNone(self.pet.gate.pending)

    def test_receipt_contains_visual_event_identity(self):
        class Socket:
            received=None
            async def send_json(self, event): self.received=event
        ws=Socket();self.pet.proactive_clients[ws]=self.lease['connection_id']
        self.p.submit(self.body());asyncio.run(self.pet.emit(self.pet.gate.events.get_nowait()))
        self.assertEqual(ws.received['event_id'],'e1')
        self.assertEqual(ws.received['response_id'],'visual:e1')

    def test_ws_lease_disconnect_cleanup(self):
        with self.client.websocket_connect('/proactive-events',headers={'Authorization':'Bearer test-only'}) as ws:
            lease=ws.receive_json();ws.send_json({'type':'heartbeat','connection_id':lease['connection_id']})
            self.assertEqual(ws.receive_json()['type'],'heartbeat')
            self.assertTrue(self.p.alive(lease['connection_id']))
        self.assertIsNone(self.p.connection)


if __name__=='__main__': unittest.main()

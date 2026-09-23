# Visual proactive audio contract (offline implementation, not deployed)

Existing voice result API requires real ASR final. Visual observations MUST NOT fabricate that final or open a second speaker. This optional transport uses the existing mechanical sounds and TurnGate. It never moves motors or identifies a person's internal emotional state. Agent policy selects stable smile → happy; possible distress → ack and playful observation → curious are later policy choices, not inference performed here.

## Authentication and lease

Both processes load a locally provisioned shared secret from `HAIFENG_PROACTIVE_TOKEN`; absent/empty disables this interface. Never commit/log the secret or expose it in the UI. Voice binds loopback only. Dedicated `ws://127.0.0.1:7860/proactive-events` requires `Authorization: Bearer <secret>` and rejects browser Origin. Only one lease is active; replacing it cancels that connection's pending proactive output.

Server hello: `{type:"proactive_state",connection_id,session_id,turn_id,epoch,input_id}`. Send `{type:"heartbeat",connection_id}` every 500 ms; server replies `{type:"heartbeat",session_id,turn_id,epoch,input_id}`. At 1.5 seconds without valid heartbeat the lease fails closed; a late heartbeat cannot revive it. Reconnect only for NEW observations. Events observed before the new connection are rejected.

## POST /api/proactive-sound

Same Bearer header. JSON fields:

```json
{"event_id":"unique-source-session-and-event-id", "connection_id":"from-hello", "session_id":"from-hello", "expected_epoch":0, "semantic_id":"happy", "event_timestamp":1790000000.0, "ttl_ms":2000}
```

`event_timestamp` is the ORIGINAL visual observation's Unix seconds (not request time). TTL is finite, positive and ≤2000 ms, future timestamps rejected. Allowed semantic IDs: happy, ack, curious. No arbitrary PCM, file, TTS or longer utterance fields. Existing sounds unchanged.

Returns `{accepted,event_id,response_id,reason}` plus unchanged voice identity on success. `response_id` is `visual:` + event_id. Rejected events are not retried. Valid but busy/muted/cooldown observations are consumed for deduplication, so they cannot be replayed later. Successful proactive playback does NOT increment epoch, synthesize final, alter answered, or emit turn_changed. It uses an independent response in the current voice epoch. Genuine speech/stop/mute still invalidate it.

Admission rejects: invalid timing/semantic/ID; disconnected or pre-connection observations; expired/future event; old session/epoch; duplicate; muted; hearing/recognizing or queued ASR; no capture in 200 ms; less than 1 second of quiet; less than 1 second since epoch change; final voice response priority for 2.5 seconds; pending audio; 8 second global proactive cooldown; insufficient TTL to finish the unchanged short sound plus 50 ms.

Pre-VAD input RMS ≥0.008 marks recent activity; the 20 ms output callback rechecks that activity, live lease, recent capture, epoch, mute and deadline. This conservatively yields to sound before full VAD detects speech, but is NOT acoustic echo cancellation or proven room-level speech onset detection. Noise or speaker echo may suppress a proactive sound. No claim of physical conversational quality has been made.

## Receipts and failure

Dedicated WS receives visual `output_status` only: `{type,event_id,response_id,session_id,turn_id,epoch,input_id,status,reason,at}`; `at` is voice process monotonic seconds (diagnostic, not event timestamp). Status is queued/started/completed/dropped/interrupted. Completed reason `last_buffer_submitted` means audio buffer submission, not proof of audible physical output. A failed receipt send clears the lease and cancels pending output. Identity, timeout and stop checks remain in the audio callback; it cannot bypass them by delayed queue processing.

## Tests / deployment boundary

Run voice unittest discovery in the isolated voice environment. Tests create Companion without lifespan, use fake clocks and NumPy output buffers; they never open microphones or speakers. Existing voice tests remain included. No production restart, secret installation, live visual request, or physical playback is part of this change. Deployment must be coordinated by the single audio owner after independent QA and Agent integration. Existing UI is unchanged.

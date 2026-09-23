# Pet motion integration

One `MotionExecutor` is owned by the Agent service. It is the sole action
consumer; do not instantiate competing executors or stream SDK motion alongside
it. This package does not alter the daemon, own USB, or control microphone/TTS.

```python
from pet_motion import MotionExecutor

motion = MotionExecutor()  # dry_run=True; no connection or physical request
await motion.set_turn("voice:session-id:3")
receipt = await motion.submit("attention", "voice:session-id:3", 5,
                              request_id="response-id")
result = await motion.wait(receipt.request_id)
await motion.cancel()  # bypass queue; stop only our current UUID
await motion.close()
```

`set_turn` takes a nonempty opaque string. Same token preserves current work;
changing it cancels active work and discards pending work. The service can use
`voice:<session>:<epoch>` or `vision:<session>:<decision>`. It remains responsible
for event authentication, durable deduplication, authoritative epochs, and
preventing vision from interrupting active speech. Calculate remaining TTL from
the incoming absolute expiry before submission. The adapter converts it to a
monotonic deadline; the deadline applies to queued and running work.

`submit(semantic, turn_id, ttl_seconds, request_id=None)` returns immediately for
normal actions. `queued` means accepted into the bounded FIFO, never completed.
`wait(request_id)` awaits the terminal result; `get_result(request_id)` gives the
latest immutable `MotionResult`. Fields: `request_id`, `status`, `reason`, `uuid`,
`semantic_id`. States include queued/running/completed/cancelled/expired/failed,
and immediate rejected/dry_run/noop. `stop` is reserved: it bypasses token/TTL and
queue limits, awaits `cancel()`, and returns stopped or failed. Prefer calling
`cancel()` directly for palm-stop and voice interruption. Normal motion priority
is FIFO; the service selects higher-level priority before submitting.

The queue holds at most four pending actions plus one active action by default.
Full queues are rejected (`queue_full`). A retained duplicate request ID returns
the existing result without repeating the request. History is bounded (256 by
default), not a durable exactly-once ledger. Persist terminal results in the
service before eviction; querying an evicted ID raises KeyError in `wait` and
returns None in `get_result`.

## Semantics and approval

Editable `mappings.json` is loaded at construction (or pass `mapping_path`).
Candidates reference only listed assets from `docs/reachy-mapping/actions.json`:

| Semantics | Candidate |
|---|---|
| attention / listening | emotions: attentive1 |
| thinking | emotions: thoughtful1 |
| greeting / welcome | emotions: welcoming1 |
| curious | emotions: curious1 |
| acknowledge / affirm | dances: simple_nod |
| quiet / rest | no physical motion; no goto_sleep |

These names express intent only. No claim of low amplitude, short duration,
safe return, or embedded-audio behavior has been physically verified. The
recorded endpoint offers no amplitude or duration scaling. All candidates are
unapproved by default. Live execution requires **both** `dry_run=False` and
`approved:true` for that mapping, after the action owner has tested it in an
exclusive device window. `execution_timeout` limits waiting and triggers stop;
it does not scale/truncate a trajectory safely or guarantee successful return.
Quiet/rest do not interrupt an already-running move; call cancel first if needed.

## Daemon contract and failure boundary

The transport subscribes `/api/move/ws/updates` before POSTing
`/api/move/play/recorded-move-dataset/{dataset}/{action_id}`. Only a matching UUID
`move_completed` event produces completed. Unrelated events and HTTP 200 are not
completion. On cancellation/expiry, POST `/api/move/stop` with `{"uuid":...}`,
then await a matching terminal event. The event confirms daemon termination,
not physical position. Stop cannot stop unrelated clients or recover USB.

Start requests are shielded from cancellation until their bounded HTTP response
arrives, so a late UUID can still be stopped. If the POST outcome is unknown,
there may be an orphan physical move: the executor latches a fault, discards the
queue and never retries. Event disconnect, move_failed and unconfirmed stop also
latch faults. New turns do not clear faults. Close the executor and independently
verify the device is stationary/healthy before constructing a fresh live
instance; no automatic rearm or reconnect is provided. HTTP 409/known request
rejections are reported without retries. Do not treat `available` as daemon
health: it is only local admission state.

The installed REST guard supplies measured-pose entry/return for recorded moves.
This package does not install or verify that guard; the deployment owner must
verify it before granting a live window. No implicit calibration, motor enable,
sleep, media release/acquire, sound playback, or service restart is performed.

## Validation and handoff

Run `python -m pytest tests/test_pet_motion.py -q` with the repository test
dependencies. Tests use an in-memory fake daemon and httpx MockTransport only;
they never contact localhost or hardware. They cover correlation, queue bound,
serialization, TTL, stale turns, stop during POST, disconnect, ambiguous start,
failed/stop events, default gates and catalog membership. Motion/audio/return,
real WebSocket transport and combined Agent/voice acceptance remain unverified.

Changes belong to this package and `tests/test_pet_motion.py`; integration owner
may import them without modifying executor internals. No shared Agent modules or
official SDK installation were changed.

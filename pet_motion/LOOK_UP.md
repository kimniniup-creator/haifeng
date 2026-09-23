# Explicit look_up contract (implemented, not physically approved)

Semantics are independent of attention and all recorded assets. No recorded
fallback exists. `posture_profiles.json` starts with local-Y -1.5 degrees, 1.5 s
minimum per segment, configured minjerk peak 2 deg/s; code caps 2 degrees and
3 deg/s. Native URDF head/camera fixed-frame transforms put optical +Z at head
+X (within 1e-6); negative local-Y rotation therefore lifts the forward axis.
This coordinate result still requires observed physical up-direction acceptance.

## API

Use the sole MotionExecutor with its existing queue/turn/start_deadline/budget
contract. New optional keyword `baseline_id` and MotionResult.baseline_id are
backwards-compatible additions. Normal callers use a 10-second execution budget
and preserve the original event start deadline. No caller directly sends goto.

- `look_up`: read original measured pose and diagnostics, move once, verify
  arrival and at least one second of stability, then return completed with reason
  holding_verified and a baseline_id. Keep the target; no timed automatic return.
- Repeated look_up: verify the held state and return already_looking_up with the
  same ID, without another movement or additional angle.
- `return_to_start`, baseline_id required: verify the same valid baseline and
  held state, then move to that original measured pose, verify stability and
  clear baseline. It does not mean factory neutral or all-zero joints.
- `stop` / cancel(): interrupt current UUID, pin measured joint targets and verify
  them. Never automatically return. A successfully verified existing baseline is
  retained for a later explicit return; uncertain stop/hold invalidates it and
  faults the executor. Before the first successful look_up there is no public
  baseline; an interrupted attempt retains its private original reference so a
  later look_up cannot accumulate another angle from the partial position.
- A new voice epoch cancels an active move but does not by itself move a held
  posture or erase a verified baseline. The Agent service owns association of
  baseline IDs to the authenticated voice session; IDs must not cross sessions.
- Baseline lifetime is at most 120 seconds from capture, never refreshed by
  repeated look_up or stop. Expiry rejects return and further look_up pending
  owner review; it does not silently capture a raised pose and add another angle.
- Dry-run does not create a physical baseline. Missing/incorrect/expired return
  IDs are rejected. Process restart, fault or uncertain device state invalidates
  custody; no persistent baseline is replayed after restart.

## Required diagnostics and hold behavior

An installed read-only GET `/api/state/motion-diagnostics` must expose current
and desired joints, raw/effective target pose, speech offsets, enabled/error
state and a stable read timestamp. `telemetry.py` supplies a router but never
installs itself or starts a daemon. The maintenance owner controls any native
installation/restart; no hot modification by the motion owner.

Posture execution rejects missing/stale/inconsistent diagnostics, nonzero speech
offsets, active competing moves, and pre-existing joint tracking error above
0.005 rad. It never clears offsets or enables motors automatically. Pose
acceptance remains 0.005 rad orientation/body yaw, 1 mm translation and 0.01 rad
antennas, with desired/actual head joints within 0.005 rad. These gates have not
been loosened to mask the prior probe failure.

Stop uses the native `set_head_joints` command only after the active REST UUID has
terminated, retaining the measured seven head/body joints. Native SDK WS commands
are fire-and-forget, so send success is not an acknowledgement. The adapter checks
desired joints equal the captured values, IK is disabled, actual joints stay
within 0.005 rad and antennas unchanged, continuously for one second. No audio,
camera, mode switch or Cartesian re-IK hold is used by this posture path.

## Current acceptance status / next work

The previous Cartesian micro probe failed target tracking and hold transition;
see DIAGNOSIS.md. New posture/hold implementation is tested with fake devices only.
Current communication recovery left motors disabled. A new live window requires
maintenance completion, diagnostic visibility, no competing producer or retained
offset, and enabled/healthy motors under explicit coordination. Validate command
recognition, physical up direction, target, holding, stop and explicit return
separately. Only reviewed, measured results may unlock mappings.

| Requested action | Current semantic | State |
|---|---|---|
| 抬头 | look_up | implemented; physical acceptance pending |
| 回正 / 回到刚才的位置 | return_to_start + baseline_id | implemented; physical acceptance pending |
| 停止 | stop | posture joint-hold path implemented; physical acceptance pending |
| 低头 | not assigned | candidate, not open |
| 左右看 | not assigned | candidate, not open |
| 点头 / 摇头 | existing attention candidate is not acceptance | not open |
| 情绪表情 | named recorded candidates | listed assets only, not open |

### Session retirement and owner review
`await executor.invalidate_baseline()` is required on actual voice session change or disconnect, including before the first action receipt arrives. Utterance epoch changes still use `set_turn`. Invalidation cancels pending/active work, retires any existing or pending posture origin, clears its public ID, and retains the private seed. Subsequent postures reject with `posture_session_invalidated_requires_review`; a new session cannot accumulate pitch or obtain another ID for the old origin.

Only the motion owner may call `await executor.review_reset_posture_baseline()`. Do not expose it through ordinary voice or public event routes. It returns true only with no active/queued work or latched fault, trusted diagnostics, zero offsets, joint tracking, and a full stable window at the original measured seed pose. It sends no commands. Expired seeds still require that original pose. Failure/cancellation retains retirement; faults require separate investigation. Recreating the executor loses the seed and is not evidence of physical review: the owner must physically re-establish and verify a baseline before live use after restart.

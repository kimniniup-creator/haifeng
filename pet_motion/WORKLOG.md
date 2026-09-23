# Motion owner work log

## 2026-09-24 single probe window

- Reviewed fixed code: 645c98e; independent QA passed 37 fake/HTTP tests and found
  no software blocker to the coordinator-authorized one 1.5-degree probe.
- Voice owner confirmed its current process writes no motion; integration owner
  stayed dry-run. Native 1.8.0 daemon running, motors already enabled, no errors,
  no running UUID. No media ownership or service settings changed.
- Probe aborted at first measured-pose validation, before any action payload or
  UUID: result micro_verification_failed. The raw FK rotation has determinant
  1.000506969 and max R-transpose-R error 0.0006065226, exceeding the original
  0.0001 tolerance. No physical command was sent, so there is no actual motion
  amplitude, target error or execution duration to claim.
- Final daemon/backend error null, control-loop nb_error=0, running=[]; window
  returned directly to voice owner for its separately authorized process restart.
  No probe retry. Raw local-only evidence: .runtime/pet-micro-probe-20260924.json
  in the main project. No audio/video captured.
- Fix: bounded SO(3) projection for small raw FK error, reject scale/shear/
  reflection/malformed pose; raw telemetry remains in evidence. Added the real
  rotation as a regression fixture plus rejection tests. Re-submit to QA before
  requesting a new physical window. Production approvals remain false.

## Integration dependency

Coordinator approved separating original event start deadline from bounded
execution budget. Planned compatible submit keywords: start_deadline (Unix
seconds), execution_budget_seconds (10 for micro). Queue and first POST must
still reject expired original events; never refresh their source timestamps.
Epoch/stop continue to cancel in-flight execution. This is a separate code change
after the numerical-pose fix, with independent regression coverage.

## Second authorized probe: actual target not reached

- Fixed reviewed code 03a24f9, QA 39 tests passed. Voice restart finished and its
  owner explicitly released the window; integrated backend remained dry-run.
- One goto only: UUID `5fd8a28e-0cea-4a30-bd94-dcd48b87938e`. Requested local-Y
  1.5 degrees over 1.5 seconds. UUID receipt to move_completed: 1.500 seconds.
  No return goto, no retry, no larger command, no motor enable or SDK changes.
- Measured outbound rotation from origin settled around 1.033 degrees, but the
  rotation error to the intended target was about 1.081 degrees (best sampled
  1.08015), above 0.005 rad (~0.286 degrees). Translation changed about 0.490 mm;
  measured antennas and body yaw were unchanged. Completion event was therefore
  correctly insufficient: result failed/micro_verification_failed.
- The failure path issued one measured-pose hold; set_target returned ok. Pose
  subsequently changed further: sampled origin-relative peak 1.848 degrees,
  delayed read 1.858 degrees. Thus physical hold stability is not accepted either.
  This may involve FK/IK or control accuracy, but the cause is unproven; no claim
  of damaged hardware. No threshold relaxation or automatic mapping approval.
- Final and delayed reads: daemon running/enabled, daemon/backend error null,
  control-loop nb_error=0, running=[]. Both owners received window-return messages.
  Raw local-only evidence: main-project .runtime/pet-micro-probe-20260924-second.json.
- Recheck conditions: independently review raw target vs measured matrices and
  FK/IK consistency, hold behavior and pose drift; obtain a new explicit device
  window before any further motion. Neither return nor interruption acceptance
  has been demonstrated. Real motion remains blocked; software integration may
  continue in dry-run.

## TTL split implementation

- Compatible optional submit keywords start_deadline (original Unix event expiry)
  and execution_budget_seconds (<=30, intended micro budget 10). Retain remaining
  event TTL and take the earlier admission deadline; never refresh source time.
- Dequeue and first actual dispatch after preflight check admission. Budget starts
  conservatively at dequeue, covering preflight, both legs and verification;
  epoch/stop still preempts it. No keyword retains previous whole-action TTL.
- New regression cases: expired queued request cannot start despite long budget;
  fresh request can return after event expiry; new turn cancels active budget;
  slow preflight crossing original deadline makes zero submissions; invalid
  budget/expired absolute deadlines rejected.

## Read-only diagnosis handoff

Native source and offline AnalyticalKinematics replay checked matrix ordering,
local axis, units, body yaw, minjerk default, warm/cold FK and model roundtrip.
Saved target is exactly local Y +1.5 degrees; actual rotation has cross-axis
components. Warm offline model residual ~0.010 degrees does not explain the live
~1.081-degree error. Desired-joint fields are silently dropped by native
FullState despite route flags, so tracking/offset hypotheses remain unproven.
Later stationary reads show no large continuing drift. DIAGNOSIS.md records
falsifiable hypotheses and read-only instrumentation prerequisites before any
future device window. No motion or device-state changes during this analysis.

## Explicit look_up implementation in progress

Kim requested actual action mapping, starting with an independent look_up loop.
First read of this new task found native daemon communication error before any
motion was sent. The integration/link owner recovered the existing daemon without
wake-up; it reports running with motors disabled. Native telemetry installation
and any daemon maintenance belong exclusively to that owner under coordinator
authorization; the motion owner remains frozen until handoff.

Added telemetry.py (commit b1c8b7): pure read-only backend attributes, desired and
actual joints/poses, effective target and speech offsets, stable-read timestamp;
three fake/API tests passed. It does not install itself or launch a service.

Added separate look_up/return_to_start posture path and editable profile, baseline
ID custody (120s, explicit return, no angle accumulation), one-second verified
holding, and measured-joint pinning rather than Cartesian re-IK on stop. Native
SDK commands have no ack, so pin verification checks desired/actual joints and
IK-disabled state. Profiles remain unapproved pending actual diagnostics, focused
tests, independent QA and physical command/arrival/hold/stop/return acceptance.
LOOK_UP.md is the cross-owner and second-host interface handoff.

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

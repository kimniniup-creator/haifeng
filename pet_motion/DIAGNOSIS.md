# Micro motion discrepancy: read-only findings

Date: 2026-09-24. No new motion, calibration, media operation, threshold relaxation,
SDK modification or service restart was performed for this analysis. The only
additional daemon requests were read-only kinematics-info and full-state GETs.
Offline computations instantiate AnalyticalKinematics only, never ReachyMini,
Backend or a motor controller.

## Observed result

The single authorized second probe requested local-Y +1.5 degrees. Its outbound
UUID completed in 1.500 seconds, but measured target error stayed near 1.081
degrees, so no return was sent. The measured relative rotation vector before
hold was approximately **[+0.7165, +0.7163, +0.2021] degrees**, whereas the request
was **[0, +1.5, 0]**. This is cross-axis error, not merely a shorter pure pitch.
The subsequent Cartesian measured-pose hold also changed the measured pose;
an `ok` response is therefore not evidence of a stable physical hold.
The delayed postflight pose and a later stationary read differ by only
0.000095 degrees / 0.000054 mm; there is no observed ongoing large drift between
those two later reads. This does not retroactively validate the hold transition.

## What the source and offline replay establish

The inspected native source is under the verified native Reachy Mini Control
`.venv/Lib/site-packages`, not the redirected Codex environment; daemon reports
1.8.0. Relevant SDK paths:

- `reachy_mini/daemon/app/models.py`: Matrix4x4Pose flattens/reshapes in row-major
  order; XYZRPYPose uses meters and radians, scipy Euler order xyz.
- `daemon/app/routers/move.py`: goto converts AnyPose to a matrix and forwards
  duration, antennas and body_yaw. It does not forward the interpolation field.
- `daemon/backend/abstract.py`: goto_target defaults to MIN_JERK, measures its
  starting pose and builds GotoMove. play_move does not pin the exact final frame;
  it exits its loop when elapsed time reaches duration.
- `motion/goto.py`, `utils/interpolation.py`: orientation interpolation uses the
  relative rotation `R_start.inverse * R_target`, then composes from start.
  Minimum jerk is `10t^3 - 15t^4 + 6t^5`.
- `kinematics/analytical_kinematics.py`: IK adds the head Z offset, handles body
  yaw, and FK subtracts the same Z offset. The live `/api/kinematics/info` reports
  AnalyticalKinematics, collision check false.

Our saved payload decodes to exactly +1.5 degrees around the measured local Y,
with unchanged translation and explicit measured body_yaw/antennas. No evidence
of transpose, flattening, degrees/radians, or unintentional zero-body-yaw errors
was found in that path. Requested minjerk agrees with the backend default despite
the router omission; it does not explain the observed cross-axis error.

Offline native IK→FK of the saved requested target after convergence gives
**0.00947 degrees / 0.03317 mm** residual, with no body-yaw change. Both automatic
body-yaw true and false produced the same result here. A warmed 151-sample
minimum-jerk path using the normal three FK iterations per sample peaked at
**0.01004 degrees** model residual. Cold three-iteration FK can be very inaccurate
from its sleep seed, so a cold result must not be confused with a continuously
running daemon's warm FK.

On a later read-only joint snapshot, converged FK of measured joints agrees with
the reported pose within **0.00122 degrees / 0.00051 mm**. IK of that reported pose
differs from measured joints by at most **0.03681 degrees**. These computations
do not explain a one-degree physical target residual through the ideal static
model alone, and they do not prove motor tracking is at fault.

## Remaining, falsifiable alternatives

1. **Target joint tracking / controller behavior:** compare actual desired joint
   values and encoder values at each sample, including mode, saturation and
   calibration. Current evidence has actual poses and a later actual-joint
   snapshot, but no contemporaneous desired-joint telemetry. Thus neither motor
   deadband/backlash nor a controller issue is established.
2. **Offsets before IK:** `update_target_head_joints_from_ik` composes nonzero
   `_speech_offsets` in world coordinates before solving IK. Old Conversation
   code enables wobbling. Native `release_media` stops the media pipeline but
   does not itself reset those offsets. Current voice software sends no motion,
   but that alone does not prove the daemon's retained offsets are zero. The
   public status endpoint does not expose them. No reset was attempted. Outbound
   and post-hold residual vectors do not match a single constant offset, so a
   constant-offset explanation is not proven either.
3. **Cartesian hold vs joint hold:** set_target sends the measured Cartesian pose
   back through IK, rather than freezing measured encoder targets. This can change
   joint targets, especially with offsets or modeling/tracking error. Native
   enable_motors happens to pin measured joints directly, but calling it would
   change device state and is not part of this analysis or a proposed shortcut.
4. **Telemetry lag/final-frame timing:** goto exits before an exact endpoint write.
   Normal minjerk endpoint truncation is expected to be small, but no target/time
   sample proves its size in this run. Instrumentation is needed before blaming
   scheduling or loosening the physical threshold.

## Concrete diagnostic gap and next minimal conditions

`/api/state/full` advertises `with_target_head_pose`, `with_target_head_joints` and
`with_target_body_yaw`. The route constructs those dictionary keys, but the
native FullState model does not declare them and Pydantic drops them. A read-only
request with all three enabled returned none of those fields. This is a verified
software observability gap, not absence of target state inside the controller.

Before a new physical window, arrange a separately reviewed **read-only** source
of desired joints, actual joints, target pose before/after speech offsets, offset
values, active UUID and timestamps. Check its output offline first. Then compare
the saved payload through IK against the daemon's desired joints and actual
joints: mismatch before actuator dispatch points to transforms/offsets; matching
desired values with encoder error points farther down the control path. A
stationary observation should precede another motion. Any subsequent motion or
change of hold strategy requires a fresh coordinator window; no automatic retry
or production approval follows from this document.

Local raw evidence (ignored, not uploaded):

- `.runtime/pet-micro-probe-20260924-second.json`
- `.runtime/pet-micro-offline-ikfk-20260924.json`
- `.runtime/pet-micro-current-joints-readonly-20260924.json`
- `.runtime/pet-micro-joint-analysis-20260924.json`

Software TTL integration is independently ready in commit 0b999ac and passed
44 tests plus independent QA. Real automatic motion remains disabled.

## 2026-09-24 post-restart read-only tracking evidence
Maintenance owner handed over a read-only window for daemon 41652; Kim is away, so motion and torque changes remain prohibited. Five GET diagnostic samples spaced 0.5 seconds apart reported stable_read=true, enabled, error=null, active_move_depth=0 and all six speech offsets zero. Desired and effective Cartesian targets were the same, approximately identity; ik_required=true.

Actual minus desired head/body joints were approximately [-0.527, 1.191, 2.500, -6.718, -0.225, -6.894, 10.058] degrees. Maximum joint error remained 10.058 degrees across samples. Measured Cartesian target error settled near 8.645 degrees and 8.518 mm. This fails the existing 0.005-radian joint tracking preflight without issuing any command. No threshold was changed.

This establishes current target tracking mismatch; it does not establish motor torque, hardware failure, or the cause of the earlier 1.08-degree probe error. Zero offsets only describe these new samples. Raw evidence is intentionally ignored at `.runtime/posture-readonly-after-restart.json`. Next: maintenance/owner investigation with an observable device window; no automated repeat, enable/disable, SDK writes, or pose correction was performed.

## 2026-09-24 bounded source/log diagnosis (read-only)
**Conclusion:** current target tracking mismatch is confirmed; physical root cause remains undetermined. It is not valid to diagnose a stuck IK loop from `ik_required=true`.

Evidence:
- Three new paired diagnostics/status GETs at Unix 1790188372.79–1790188374.81 show max joint error still 10.058 degrees. Joint feedback changes in discrete steps; Python loop stats change around 32.27–32.53 Hz, native controller period around 20 ms, read duration around 2 ms and write duration around 0.27 ms. This argues against a wholly frozen Python loop or entirely frozen feedback snapshot. It does not prove writes reached the motors or that torque is physically enabled.
- Authoritative native log: `\\localhost\C$\Users\12246\AppData\Local\com.pollen-robotics.reachy-mini\logs\Reachy Mini Control.log`. Its timestamps are UTC. In the inspected 18:18:30 onward segment (2341 lines at capture), startup reports Disabled at 18:18:40; POST enable and POST wake_up occur at 18:18:50. No backend WARNING/ERROR, motor communication error or IK error matched in that bounded segment. Desktop wraps all stderr in WARN, including HTTP 200 logs: that wrapper is not itself a hardware warning. Older `.runtime/daemon.stderr.log` is not the current process log and must not be used as evidence of current bus failure.
- Native `RobotBackend._update` dispatches existing desired joints to controller setters first, provided `_torque_enabled` and nonzero `_current_head_operation_mode`; it then reads cached motor positions, performs FK, and computes desired joints if `ik_required`. `update_target_head_joints_from_ik` updates desired joints and effective target but does NOT clear that flag. One-tick scheduling latency cannot alone explain a sustained mismatch minutes later.
- `get_status` copies cached control mode/error; its ready/last_alive fields are not refreshed there. `nb_error` is reset each stats period and mainly counts caught RuntimeErrors in the read/update block, not verified physical arrival. Hardware-error polling logs warnings without necessarily setting backend.error. Therefore enabled/error-null/zero recent errors are insufficient acceptance evidence.
- Current target/effective target equality, zero offsets and valid near-neutral desired joints show no current speech-offset composition discrepancy. UI wake-up explains why a neutral desired pose appeared after startup; it does not explain failure to converge to it. Current samples cannot reconstruct the earlier micro probe's desired joints.

Offline source checks: `pet_motion/check_native_semantics.py BACKEND_ROOT` extracts only selected function ASTs into fake objects, without importing native SDK/controller or touching hardware. Four checks passed: successful IK leaves flag true and populates targets; enabled position-mode loop dispatches expected joints; internal torque disabled skips position dispatch; current mode skips position dispatch. This demonstrates interpretation and conditional behavior, not which hidden branch the live process uses. Audited SHA256: abstract.py `be41653e96dbc8db81d94275a751d867e525de0845018aaecc9cc39a65d65b87`, robot/backend.py `7d799da6de711fae6622ceb296eaf68cd54519c034605067c5ee89f8f273ac87`.

| Candidate | Evidence / remaining gap | Smallest falsification step |
|---|---|---|
| Entire control loop or feedback frozen | Disfavored by changing feedback and period stats | Add cached tick sequence/last_alive to a reviewed diagnostic change in a later maintenance window; no live patch now |
| Wrong internal branch / motor mode | Public mode is cached; `_torque_enabled` and `_current_head_operation_mode` are not exposed | Read those cached fields via reviewed diagnostics during maintenance; no setter or restart in this task |
| Motor-controller target write or torque/actuation issue | Large persistent joint error despite loop activity; .pyd implementation and motor-side goals/torque not observed | With owner and observable device, use the existing single controller to compare motor-side goal/present position, torque and mode readback; do not open a second bus connection |
| Initialization / UI wake-up target | Enable+wake logs support target provenance | Compare pre/post startup targets in a later explicitly controlled window; repeated startup is not a harmless diagnostic |
| Current speech offsets or entirely unconsumed IK target | Zero offsets and computed effective target/desired joints disfavor these narrow explanations | Keep target/current/offset snapshots together; do not zero offsets or loosen tracking tolerance |

**Next minimal experiment:** first extend read-only cached diagnostics in a separately reviewed maintenance change to expose internal dispatch gates and tick freshness; this requires no requested pose change. Only if those gates are correct, in an observable authorized window obtain motor-side readback through the existing controller to separate goal-write failure from torque/mechanical response. Actual bus read and any motion/torque intervention are not performed or authorized by this read-only task. Do not repeat look_up while preflight fails. No POST, SDK command, torque change, restart, or native hot patch was used.

## Cached dispatch-gate extension (prepared, not deployed)
The schema-1 helper adds `torque_enabled_cached`, `head_operation_mode_cached`, `antennas_operation_mode_cached`, and `last_alive_unix`, directly from existing backend attributes. Missing fields return null (unsupported/unknown), never false or zero. No controller attribute or getter is accessed. Existing fields and route remain compatible.

The cached gate values are included in the double-read consistency check. `last_alive_unix` is sampled separately because a normal control-loop tick can change it; it is the backend's wall-clock successful-update timestamp, not the stale status-object field. Compare successive timestamp advances and sample age; wall-clock adjustment can affect age. No tick sequence is currently cached/exposed, and no sequence is fabricated. These fields diagnose the Python dispatch branch, not physical motor torque, bus acknowledgment or motor goal-register acceptance.

Interpretation after reviewed installation: false internal torque skips position dispatch; head mode 0 selects current-control rather than position dispatch; nonzero includes startup sentinel -1, so it proves only branch selection, not actual hardware mode. Enabled public mode conflicting with an internal gate is evidence to investigate, not permission to change it. Fresh last_alive indicates the update path reached its success marker, not that target tracking succeeded. Keep original measured-target thresholds unchanged.

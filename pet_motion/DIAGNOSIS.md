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

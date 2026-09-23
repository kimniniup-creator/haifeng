# Single-candidate physical acceptance plan (not executed)

2026-09-23: read-only inspection of native cached assets and installed guard.
The coordinator owns the device window; voice must hand it back before any step
below sends motion. Integration owner keeps the default dry-run gates unchanged.

## Evidence and selection

| Candidate | Recorded duration | Head rotation peak from identity / first frame | Antennas (degrees) | Adjacent WAV |
|---|---|---|---|---|
| attention: attentive1 | 4.28 s, 215 samples | 21.793 / 12.341 degrees | left -34.381 to -7.424; right 27.605 to 55.380 | absent |
| acknowledge: simple_nod | 1.82 s, 92 samples | 19.991 / 20.255 degrees | left -44.980 to 44.930; right -44.930 to 44.980 | absent |

These are target trajectories, not measured physical amplitudes. Identity is the
asset coordinate-frame identity, not a verified current robot pose. attentive1
translation ranges in mm: x [-6.682,-2.867], y [-5.272,-2.751], z [4.193,8.629];
body yaw is 1.060 degrees. simple_nod translation and body yaw are zero. Their
last-to-first head rotations differ by 2.587 and 4.684 degrees respectively;
neither is evidence of a return to the measured pre-action pose.

Prefer **attentive1 only** for the first review: its recorded antenna excursion
is smaller. Neither qualifies as a verified micro-motion. Do not automatically
substitute simple_nod because its name sounds gentle. If these target ranges are
unsuitable, stop this candidate review and design a separately bounded custom
motion; the recorded endpoint has no amplitude scaling parameter.

Asset SHA256:

- attentive1: `eac086094c388fbe9d6d704ba3705578526de3c0b6343b4774fca965d91a58e4`
- simple_nod: `3f4dd31fdcc48691386ae562bb0f53fbb7f7ec7e5969fdd0edb4d72a1ba19d50`

Cache dataset snapshots: emotions `873ae49f0b89114b7e535eff0c1f7560d21d9357`,
dances `3564295e72d41c1271f46bf5540a3fcad9d5f669`.
Installed native guard SHA256 matched repository source:
`6aa188e78e7315e334ccefd8d88d8801a090e81eebab7f694d48e8e20de7d6ec`.
It adds entry and return transitions of at least two seconds each, increasing
with starting-pose distance. Thus attentive1 is at least 8.28 seconds plus return
verification; compute actual transition timing from the preflight pose before
setting TTL/execution timeout. Do not let the default timeout accidentally turn
a natural-completion test into a cancellation test.

## Conditions before a live request

1. Coordinator explicitly grants the exclusive motion/audio window after voice
   owner releases it. No Conversation/SDK/gesture/background idle producer may
   issue competing motion. A supervisor can observe the robot and reach its
   physical power control. Do not call media acquire/release from this package.
2. Read current daemon/motor/control-loop state, running UUIDs and measured head,
   antenna and body pose. Record timestamps and baseline pose; verify a clear,
   stable workspace and no active move. The known stale public ready=false field
   alone does not diagnose disconnection. Any actual error, absent telemetry,
   unexpected motion or inability to confirm single ownership blocks playback.
3. Recheck exact asset hashes, audio adjacency and installed return guard. Keep
   only attentive1 under review; a temporary isolated approval config can enable
   that candidate for the supervised test without committing global approval.
4. Subscribe motion events before the POST; capture the UUID, timestamps, measured
   pose samples and observer judgment. Establish stop-by-UUID access in advance;
   software stop cannot guarantee control after USB/power failure.

## Two separate observations of the same candidate

First window: one natural playback of attentive1, with no automatic repeat.
Observe actual head/antenna extent, physical smoothness, full duration, unexpected
sound, and return to pre-action pose. Require a matching move_completed and pose
comparison, not HTTP 200. The current guard's software return bounds are 6 mm
translation and 0.04 rad (~2.29 degrees) head rotation/antenna/body yaw; report
actual measured errors and human observation rather than equating these bounds
with perceptual quality. Report whether audio was actually heard even though no
adjacent WAV was found. A missing terminal event, failed return, increasing errors,
abnormal sound or movement ends the run; no repeated trials to force success.

Only after reviewing that result and obtaining the next coordinator window:
replay the same candidate once and cancel while it is observably moving. Record
the stop request timestamp, UUID terminal event, last changing pose and subsequent
pose stability. Require cessation, no queued follow-up and no automatic return
animation. Cancellation intentionally holds current measured pose when healthy;
it does **not** promise return to the original pose. Any later return is a
separate supervised request. Do not globally approve the candidate until natural
completion, interruption and voice-window compatibility have all been assessed.

No physical playback, audio playback, device lease, service restart or mapping
approval occurred while preparing this plan.

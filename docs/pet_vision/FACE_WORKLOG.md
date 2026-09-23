# Face-cue work log / handoff

2026-09-24: Kim clarified the primary goal as seeing crying, playful behavior or smiling and responding. Created isolated `codex/pet-face-cues` worktree from main 6ecdcfc. Read-only commands and reversible local edits work; the earlier policy-denied camera startup has not been retried or bypassed.

Stages 1/2 first delivery: face quality/anonymous visibility track and stable smile event implemented. Contract agreed with integration owner: visual_cue/smile, configured confidence floor .7, 800 ms minimum, two-sided coefficient .55, usable single face, TTL1.5, global12s cooldown and held-expression latch. Backend owns all audio/policy and does not act on unknown/face_presence.

MediaPipe official face model downloaded explicitly into ignored runtime, hash pinned. Real blank-frame inference works with model_asset_buffer. Synthetic coefficient tests cover quality/multiface suppression, stable smile, cooldown, neutral release, timestamp rejection, absence renewal and track reset. No camera, image persistence, cloud media, emotion diagnosis or identity store added. Subsequent stages will use explicit provisional cue names and separate tests/commits; live recognition stays unverified until a lawful camera session and ground-truth observation are available.

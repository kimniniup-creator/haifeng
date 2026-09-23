# Vision owner handoff

Owner scope: `pet_vision/`, `tools/run_pet_vision*`, `tests/test_pet_vision*`, `requirements-vision.txt`, and `docs/pet_vision/`. Worktree is an isolated implementation branch; integration owner should merge its PR, then dispose of the execution worktree when no longer needed. Do not run this branch as a second permanent service.

Integration: use `Pipeline.process(Frame(...))` with the existing camera owner, or consume runner stdout. Unified events target `/v1/events` port 8091 using the agreed v1 schema. No speech epoch is fabricated. Source session IDs change per engine/process. `presence` is hand visibility only. Backend owns all effects and cross-source arbitration.

Acceptance: see README evidence. Software/offline inference is verified; actual fresh camera acquisition, human gestures, audio coexistence and robot response are not. Shared media was released before the probe. Only vision-owned readers were closed; no acquire/release, daemon restart or audio manipulation occurred. Media owner authorized a bounded video-only alternative; it yielded no successful frame evidence.

Next owner: integration/QA may consume fixed commit and rerun focused tests in an isolated environment. Media owner must provide a working fresh-frame source or coordinate further native video investigation before live gesture acceptance. Ask a human to show open fingers with separated thumb and hold 0.7 seconds for `palm_stop`, then move an open hand left-right-left across at least 12% of the frame for `wave`. Expected first evidence is event metadata; final movement/TTS acceptance belongs to backend and motion owners.

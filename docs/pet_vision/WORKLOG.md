# Vision work log

- Read Kim contract and global orchestration preferences; inspected actual Python 3.12 runtime and native SDK 1.8.0 through native AppData path. Worked in a background worktree, leaving shared main and audio processes untouched.
- Aligned v1 schema and 0.7 configured-confidence semantics with integration owner. Inspected native shared IPC reader and absence of REST frame endpoint. No face database or raw media persistence introduced.
- Installed isolated MediaPipe environment, downloaded/hash-checked official model, implemented deterministic gesture engine and real local model adapter. Tests use generated landmarks; official sample inference ran solely in memory and found two hands.
- 17 focused tests passed. Synthetic event runner emits stop, presence, leave, return and wave; HTTP test validates authenticated metadata delivery to a local fake receiver.
- Shared-reader attempt exposed pre-existing released media and no available stream; closed only owned reader. Added fail-fast media checks and hard deadlines. Audio owner authorized bounded raw video alternative; no fresh-frame result obtained. Post-probe daemon remained running/error-free; live acceptance remains open.
- A repeated bounded diagnostic with the Windows-confirmed explicit device name also timed out after imports and before reader opening. This invalidated the narrower initial inference that only device enumeration was blocked; native GStreamer initialization is also implicated. Stopped further native attempts and preserved the media owner's state.

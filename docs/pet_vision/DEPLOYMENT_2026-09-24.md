# Continuous vision deployment evidence

Checked at 2026-09-24 00:35:12 +08:00. This is a point-in-time operational record, not a guarantee of future process state.

## Deployed source and validation

- Authoritative checkout: `D:\海风`, main commit `50762ebb49cb14208ddb1e792623f9b6eae84ecb` (PR #6 merged).
- Continuous implementation: `26466cd4e8ac8eeb5543dfa5298ca3f943febf7d`; independent focused QA reported 57 passed, zero skipped. Device ownership, stalled-process cleanup, log rotation and receipt-field filtering were covered without opening a camera during QA.
- Runtime: `D:\海风\.runtime\vision-env\Scripts\python.exe`, isolated Python 3.12.13, dependencies from `requirements-vision.txt`.
- Model: `D:\海风\.runtime\vision-models\hand_landmarker.task`, SHA256 `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`.
- The first launch with an absolute Chinese model path failed in the MediaPipe native file loader before camera opening and exited. The corrected launch uses the relative model argument below and working directory `D:\海风`. No failed-launch reader remains.

## One deployed producer tree

| Role | PID | Parent PID |
| --- | ---: | ---: |
| Vision Python launcher/root | 5124 | 32852 |
| Vision producer interpreter | 41712 | 5124 |
| Camera Python launcher | 50740 | 41712 |
| DirectShow reader interpreter | 39848 | 50740 |

These are one producer and one camera reader, each with a Python environment launcher. No other `run_pet_vision` process was present. The named mutex excludes cooperating pet-vision readers in the same Windows session; it does not control arbitrary external camera software.

The process runs hidden, from the authoritative checkout:

```powershell
& D:\海风\.runtime\vision-env\Scripts\python.exe tools/run_pet_vision.py --provider pet_vision.ipc:leased_opencv_frames --continuous --send --model .runtime/vision-models/hand_landmarker.task --event-log .runtime/vision-events.ndjson
```

The launcher reads the `vision` field of ignored `.runtime/pet-local-tokens.json` into `PET_VISION_TOKEN` locally, restores its previous environment afterwards, and never prints or passes the token as a process argument. It does not start or alter the audio service, backend or robot daemon. Motion remains dryrun; no motion-enable argument was introduced.

Stop this exact running tree:

```powershell
taskkill /PID 5124 /T /F
```

For later use, check the saved root still names this producer before stopping it:

```powershell
$visionRootPid = [int](Get-Content D:\海风\.runtime\vision-runner.pid)
$visionRoot = Get-CimInstance Win32_Process -Filter "ProcessId = $visionRootPid"
if ($visionRoot.CommandLine -like '*run_pet_vision.py*') {
    taskkill /PID $visionRootPid /T /F
}
```

Do not kill all Python processes. There is no automatic reconnect, scheduled task or reboot autostart. Restart requires the existing exclusive video ownership arrangement and official media remaining released.

## Real delivery and concurrent health

At the snapshot, the deployed producer had delivered **109 real no-hand events across 95.378 seconds**, all with `accepted` receipts, zero other statuses. No synthetic events were fed to production. The event kind is legacy wire `presence` with `payload.basis='hand'`; the product meaning is hand_presence / 手部可见性.

| Component | Observed state |
| --- | --- |
| Voice, port 7860 | listening, error null, capture_age_ms 16, capture_frames 52382, dropped_frames 0, semantic_agent_connected true |
| Pet backend, port 8091 | hand_visibility not_visible, voice_connected true, voice_link_error null, motion_fault empty |
| Robot daemon, port 8000 | running, daemon/backend errors null, nb_error 0, media_released true |
| Vision | one running producer tree above, real DirectShow frames processed locally |

Before deployment, voice capture_frames was 46375 with zero dropped frames. These counters establish continued capture during the observation, not speech-recognition accuracy or acoustic quality.

An earlier bounded send run separately tested disconnection semantics: 264 distinct frames over 60.36 seconds, two slow reads rejected, 66 real no-hand events accepted; backend hand_visibility changed unknown → not_visible → unknown after the reader exited and the lease expired. There were no leftover readers before the continuous launch.

## Local-only evidence and limits

Ignored local metadata files:

- `.runtime/vision-runner.pid` and `.runtime/vision-deployment.json`: root process and source information.
- `.runtime/vision-events.ndjson`: event/receipt metadata, rotating at 1 MiB with one backup.
- `.runtime/vision-live.stderr.log`: initialization/error diagnostics; `.runtime/vision-live.stdout.log` is not a media stream.
- `.runtime/vision-deployment-verification.json`: filtered service counters and event totals, without conversation text or credentials.

No camera frame, audio waveform, model download, token or raw runtime log is committed with this evidence. Camera pixels travel only through a local anonymous pipe to local inference. Source timing is conservative read-start time because this OpenCV path does not expose sensor PTS; it is not a measurement of sensor-to-event latency.

No instructed human gesture with ground truth was performed. Live visible-hand detection, wave/palm-stop accuracy, long-term USB/audio coexistence and physical robot actions remain unverified. `not_visible` means no accepted hand detection, not “no person” or “person left”. Physical motion remains disabled pending its separate acceptance.

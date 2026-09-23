# Desktop startup must not wake the robot

Offline source patch for official Reachy Mini Control **0.9.32**, upstream commit
`f520136ffe9b54ba6e34a6d5b4da4781cfd55ab8`. It has not been installed in the running desktop app.

## Cause and correction

The Rust launcher passes `--no-wake-up-on-start`; USB therefore starts the daemon
without its own wake animation. WiFi/external startup also uses `wake_up=false`.
However, `src/views/starting/StartingView.tsx` independently POSTs motor enable
and wake after scan completion. The launch flag does **not** suppress this frontend
callback. Earlier statements that reopening the desktop could not wake the robot
were incorrect: they checked only the daemon layer.

The observed native log at 2026-09-23 18:18:40 UTC starts disabled, followed at
18:18:50 by enable and wake POSTs. This matches the frontend sequence. Attribution
to that exact client is an inference: the historic socket no longer has a process owner.

No auto-wake configuration switch was found in this pinned source. The patch keeps
scan completion passive and displays an explicit **Wake up / open controls** button.
Only clicking it can run the prior wake sequence. An already-enabled robot opens
controls without a movement request; disabled mode enables then wakes; unknown
mode fails closed. A ref prevents duplicate concurrent clicks. HTTP errors do not
advance to controls. Connection completion never changes torque, even if already enabled.

## Callback trace

- `src/hooks/daemon/useDaemon.ts`: USB native start; WiFi/external start with `wake_up=false`.
- `src-tauri/src/python/mod.rs`: native `--no-wake-up-on-start`.
- `src/views/starting/StartupView.tsx`: daemon-ready and scan-complete gates,
  `postReadyStartedRef`, then `runPostReadySequence()`.
- `src/views/starting/hooks/usePostReadySequence.ts`: state stream/app catalog
  synchronization, completion hold, then parent's `onScanComplete`.
- `src/hooks/daemon/useDaemonReconciliation.ts`: webview recovery sets STARTING;
  `src/hooks/system/useViewRouter.tsx` routes it through the same StartingView.
- Retry and a new connection repeat that pipeline. The final callback now only
  sets local UI state; repeated completion cannot invoke the click handler.
- Explicit wake/sleep code in `useWakeSleep.ts` and the settings daemon-start
  button remain unchanged. These are separate user-driven paths, not a global
  motor-output interlock. No background wake call was found in this source search.

## Reproduce without devices

Create an **offline** worktree of the upstream commit. Do not point at an installed
application or a checkout serving the live desktop. The script verifies commit and
source hashes, defaults to a dry run, and never builds, installs or restarts anything.

```powershell
python patches/reachy_desktop_no_autowake/apply.py D:/offline/reachy-desktop
python patches/reachy_desktop_no_autowake/apply.py D:/offline/reachy-desktop --apply
npm install --prefix .runtime/desktop-autowake-test typescript@5.9.3 --ignore-scripts --no-audit --no-fund
node patches/reachy_desktop_no_autowake/test.cjs D:/offline/reachy-desktop ./.runtime/desktop-autowake-test/node_modules/typescript/lib/typescript.js
```

Focused test executes the patched TSX under mocked React/state/network/timers. It
covers disabled/enabled/missing/other mode, repeated completion, explicit click,
duplicate click, changed mode and both HTTP failure points. Named startup scenarios
exercise their shared final callback, **not full end-to-end Tauri startup**; the path
from recovery/startup to that callback is source-traced above.

## Deployment plan and remaining verification

1. Independent QA reviews the pinned diff, callback paths, and focused tests.
2. In an isolated upstream checkout use its existing Yarn lockfile to install,
   typecheck, test and build. Do not run daemon/sidecar scripts in this maintenance window.
3. Before deployment, visually verify the new gate at desktop and narrow widths in
   an isolated mocked frontend. Full application build and visual QA are pending;
   passing the focused tests is not a desktop UI acceptance claim.
4. In a separately authorized maintenance window, preserve the current installer,
   build/package the reviewed version and replace the desktop through its normal
   install process. Avoid patching bundled production assets in place.
5. Verify first connection, disconnect/reconnect and webview recovery produce zero
   enable/wake POSTs. Test the explicit wake button only with physical supervision
   and the sole motion owner. Restore the saved installer to roll back.

The manual wake path retains upstream animation wait/fallback behavior (including
timeout-based UI continuation); this patch does not certify physical completion,
holding, or failure handling of that existing sequence. It also does not disable
other clients such as legacy bridge 8088. Production remains unchanged.

# Official-client expression return patch

Scope: Reachy Mini Control 0.9.34, its reachy-mini 1.8.0 or 1.11.0 environment (exact router hash required). The project SDK/bridge and firmware are unchanged.

The original recorded-expression route starts playback directly, without interpolation from the measured pose or a return segment. The native player silently ignores a request while another motion owns its lock. Cached recordings have different start/end poses; chin_lead ends roughly 13 degrees away in pitch from its start. These explain missing return/unsafe handoffs, but do not explain USB disconnection by themselves.

This patch adds a single composite move: measured starting pose → recording start → original recording → measured starting pose. Entry/return use minimum-jerk interpolation with peak transition limits around 30 deg/s and 2 cm/s, at least 2 seconds each. Original recording motion is unchanged. It returns to the pose before that expression, not a calibrated factory-neutral pose. A recorded request while any REST motion/return is active receives 409. Disabled/disconnected robots receive failure; there is no automatic motor enable, reconnect or calibration. Cancelling holds the measured pose only if communication remains healthy. A failed return produces move_failed rather than move_completed. Reservation cleanup includes cancellation before the task starts.

The guard applies to recorded-expression requests, not arbitrary SDK streaming or the separate controller. Do not issue controller/SDK movement concurrently. Official frontend error presentation and its fixed command debounce are unchanged.

## Install and rollback

Close the official client completely and run using its own Python:

```powershell
& "$env:LOCALAPPDATA\Reachy Mini Control\.venv\Scripts\python.exe" D:\海风\patches\reachy_expression\install.py
# Undo, with the client closed:
& "$env:LOCALAPPDATA\Reachy Mini Control\.venv\Scripts\python.exe" D:\海风\patches\reachy_expression\install.py --rollback
```

Installer checks SDK version, exact original router SHA256, and port 8000 is closed. The original router is backed up alongside it as move.py.haifeng-original. Official updates may replace this patch; do not blindly reinstall on another version. No secrets or media are included.

## Verification on 2026-09-23

12 unittest cases passed in the actual official SDK environment, including its installed route, actual native play_move loop against a fake backend, return interpolation, overlap rejection, cancellation before/during motion, disconnect, disabled motors, invalid data, native skipped playback, SDK 1.11 stop requests and cleanup. These are software tests, not physical robot acceptance.

```powershell
& "$env:LOCALAPPDATA\Reachy Mini Control\.venv\Scripts\python.exe" -m unittest discover -s D:\海风\patches\reachy_expression -p test_guard.py -v
```

Installed router SHA256: ccd1ab534d64d60bea9edf17a0a62d1892b39b9c12514b34804e395fe85edd40.

Physical acceptance remains blocked: on the fresh client launch, before any expression was sent by the agent, logs at 2026-09-23 07:41:58 UTC show USBError Pipe error in DoA read, camera stream failure, then errors reading all nine motors and daemon state error. This reproduces independent of the expression flow. UI Ready must not be used as connection proof. Requested a powered-off cable reseat/direct USB connection from the user before further hardware testing. No large test motion, reset or firmware write was attempted.

The desktop updater upgraded its environments to 1.11.0 at 07:42 UTC and replaced the first patch installation. Router content hash is identical in both versions; the installer now supports both verified versions. Tests were rerun on 1.11.0 and the patch reapplied, including its added native stop flag. User confirmed a physical cable/power reconnection; communication subsequently recovered, further motion verification follows.

## Final hardware check after reconnect

User confirmed physical reconnection. Official updater changed the daemon to 1.11.0; patch was adapted, its native stop flag tested, installed again, and client restarted. Installed helper SHA256 matches source: 6aa188e78e7315e334ccefd8d88d8801a090e81eebab7f694d48e8e20de7d6ec.

Small antenna test: origin -0.1902136 rad, requested -0.1402136 rad (+0.05 rad / 2.86 deg), actual -0.1626020 rad (+0.0276117 rad / 1.58 deg). Target error 0.0223883 rad exceeds the probe's 0.015 rad criterion. Return measured exactly at initial encoder value; other antenna unchanged. No larger recorded-expression test was sent after this failure. This does not by itself diagnose broken hardware; it is an unpassed positioning check.

At final observation daemon 1.11.0 was running, ready, enabled, error null, control-loop nb_error=0, no running moves. Continuous full-expression/physical acceptance remains unverified. The earlier disconnected-state observation above is historical, superseded by this recovered connection state. Raw motor positions and events are local .runtime/expression-small-motion.json; no environmental recording captured.

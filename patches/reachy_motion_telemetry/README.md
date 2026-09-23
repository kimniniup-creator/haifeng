# Read-only native motion diagnostics

Adds only GET `/api/state/motion-diagnostics` using the existing state router and
`get_backend` dependency. It inherits the daemon's existing middleware and access
boundary; it adds no listener, token bypass, motor call, setter or lifecycle hook.
Native SDK 1.8.0 fields were inspected: the helper reads ordinary cached attributes
and copies array values, never device getters. `stable_read` compares two copies;
it is not a transaction or proof of physical stability.

The maintenance owner must stop the existing backend with `goto_sleep=false`,
release voice/video owners, and verify there is no concurrent native writer.
Use the verified native site-packages path (UNC on this Codex host), not a
redirected SDK copy. The installer does not restart anything.

```powershell
python patches/reachy_motion_telemetry/install.py --site-packages '<native site-packages>' --backup-dir '<new ignored backup directory>'
```

The installer compiles text before writing, saves originals and SHA256 metadata,
and atomically replaces each file with a new inode to avoid uv hardlink pollution.
Repeated identical installation is a no-op; different existing patches fail closed.
The helper is copied from `pet_motion/telemetry.py` (motion owner b1c8b7).

After the existing HTTP process has stopped, start exactly one native daemon with
no wake-up, no media capture, and the same or narrower listen address. Verify
SDK version, the new GET, existing state/status routes, motor mode disabled,
and no control-loop errors. Never treat HTTP job completion alone as recovery.
Restore the independent voice/video owners only after media ownership is clear.

Rollback while the daemon is stopped:

```powershell
python patches/reachy_motion_telemetry/install.py --backup-dir '<same backup directory>' --rollback
```

Rollback refuses to overwrite subsequent unrelated changes. Then restart the
single native daemon without wake-up and recheck existing routes. Never publish
backup manifests, runtime logs, local credentials, or user media.

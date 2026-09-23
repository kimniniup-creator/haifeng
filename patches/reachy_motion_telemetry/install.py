"""Explicit, reversible native SDK patch; never starts a service or opens hardware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

MARKER = b"# haifeng: read-only motion diagnostics v1"
SUFFIX = b"\n\n" + MARKER + b"\nfrom haifeng_motion_telemetry import make_router as _haifeng_motion_router\nrouter.include_router(_haifeng_motion_router(get_backend))\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    # Replacing the directory entry avoids editing uv's shared hard-linked inode.
    handle, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install(site, backup, helper):
    site, backup, helper = Path(site).resolve(), Path(backup).resolve(), Path(helper)
    state = site / "reachy_mini/daemon/app/routers/state.py"
    target = site / "haifeng_motion_telemetry.py"
    original = state.read_bytes()
    source = helper.read_bytes()
    compile(original.decode("utf-8"), str(state), "exec")
    compile(source.decode("utf-8"), str(helper), "exec")
    if MARKER in original:
        if target.read_bytes() != source or not original.endswith(SUFFIX):
            raise RuntimeError("Existing patch differs; inspect before changing it")
        return "already_installed"
    if b'router = APIRouter(prefix="/state")' not in original or b"get_backend" not in original:
        raise RuntimeError("Unsupported native state router")
    if backup.exists():
        raise RuntimeError("Use a new backup directory; never overwrite recovery evidence")
    backup.mkdir(parents=True)
    files = [(state, original, original + SUFFIX),
             (target, target.read_bytes() if target.exists() else None, source)]
    entries = []
    for index, (path, old, new) in enumerate(files):
        if old is not None:
            (backup / f"{index}.original").write_bytes(old)
        entries.append({"relative": path.relative_to(site).as_posix(), "original": old is not None,
                        "original_sha256": digest(old) if old is not None else None,
                        "installed_sha256": digest(new)})
    (backup / "manifest.json").write_text(json.dumps({"site": str(site), "files": entries}, indent=2), encoding="utf-8")
    # Install dependency first, then expose the router. Roll back any partial write.
    try:
        atomic_write(target, source)
        atomic_write(state, original + SUFFIX)
    except Exception:
        for path, old, new in files:
            if old is not None:
                atomic_write(path, old)
            elif path.exists():
                path.unlink()
        raise
    return "installed"


def rollback(backup):
    backup = Path(backup).resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    site = Path(manifest["site"]).resolve()
    checked = []
    for index, entry in enumerate(manifest["files"]):
        path = (site / entry["relative"]).resolve()
        if not path.is_relative_to(site):
            raise RuntimeError("Backup path leaves the SDK directory")
        if digest(path.read_bytes()) != entry["installed_sha256"]:
            raise RuntimeError("Installed file changed; refusing to overwrite unrelated work")
        old = (backup / f"{index}.original").read_bytes() if entry["original"] else None
        if old is not None and digest(old) != entry["original_sha256"]:
            raise RuntimeError("Backup checksum mismatch")
        checked.append((path, old))
    for path, old in checked:
        if old is None:
            path.unlink()
        else:
            atomic_write(path, old)
    return "restored"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-packages")
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if args.rollback:
        print(rollback(args.backup_dir))
    else:
        if not args.site_packages:
            parser.error("--site-packages is required for installation")
        helper = Path(__file__).resolve().parents[2] / "pet_motion/telemetry.py"
        print(install(args.site_packages, args.backup_dir, helper))

"""Hash-locked atomic patch installer. Stop Conversation App before installation."""
import argparse
import hashlib
import os
from pathlib import Path
import socket
import tempfile

HASHES = {
    "main.py": "cf5fe85fe990c198551286c6e2ed013be907605ba644fd79ed881be1453b66de",
    "console.py": "2ac89e113d3029186b21557f058ccafc0bb93e0f66da3ab8f447cf7b301eca49",
}


def transform(name, source):
    if name == "main.py":
        anchor = '    # Putting these dependencies here makes the dashboard faster to load'
        assert source.count(anchor) == 1
        source = source.replace(anchor, '    from reachy_mini_conversation_app.voice_runtime import acquire_single_instance\n    acquire_single_instance()\n' + anchor)
        source = source.replace('    app = ReachyMiniConversationApp()', '    from reachy_mini_conversation_app.voice_runtime import acquire_single_instance\n    acquire_single_instance()\n    app = ReachyMiniConversationApp()')
        return source
    start = source.index('    async def record_loop(self) -> None:')
    end = source.index('    async def play_loop(self) -> None:', start)
    source = source[:start] + '    from reachy_mini_conversation_app.voice_runtime import record_loop\n\n' + source[end:]
    anchor = '        @rpc.method("conversation.say")'
    assert source.count(anchor) == 1
    return source.replace(anchor, '        @rpc.method("conversation.audio_health")\n        def _rpc_audio_health(_params):\n            from reachy_mini_conversation_app.voice_runtime import audio_health\n            return audio_health(self)\n\n' + anchor)


def atomic_write(path, data):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".tmp-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def install(site, rollback=False):
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 7860)) == 0:
            raise RuntimeError("Stop Conversation App before patching port 7860")
    package = site.resolve() / "reachy_mini_conversation_app"
    changes = []
    for name, digest in HASHES.items():
        path = package / name
        backup = path.with_suffix(".py.voice-runtime-original")
        original = backup.read_bytes() if backup.exists() else path.read_bytes()
        if hashlib.sha256(original).hexdigest() != digest:
            raise RuntimeError(f"Unsupported original {name}")
        patched = transform(name, original.decode("utf-8")).encode("utf-8")
        if path.read_bytes() not in (original, patched):
            raise RuntimeError(f"Independent changes in {name}; refusing overwrite")
        compile(patched, str(path), "exec")
        changes.append((path, backup, original, patched))
    helper = Path(__file__).with_name("voice_runtime.py").read_bytes()
    compile(helper, "voice_runtime.py", "exec")
    # Helper first, then importers. Atomic replacement preserves uv hardlinks.
    if not rollback:
        atomic_write(package / "voice_runtime.py", helper)
    for path, backup, original, patched in changes:
        if not backup.exists():
            atomic_write(backup, original)
        atomic_write(path, original if rollback else patched)
    print("Voice runtime", "rolled back" if rollback else "installed", package)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", type=Path, required=True)
    p.add_argument("--rollback", action="store_true")
    args = p.parse_args()
    install(args.site, args.rollback)

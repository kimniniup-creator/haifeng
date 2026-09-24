"""Make the conversation app's voice-activity detection tunable.

The upstream app hardcodes ``ServerVad(type="server_vad", interrupt_response=True)``
with no threshold, which is unusable in a noisy room: ambient sound is read as
the user starting to talk, the player queue is flushed, and the robot is cut off
before it finishes a sentence. This patch reads the four ServerVad knobs from the
environment and defaults them to noisy-room values.

Idempotent. Keeps a .orig backup and verifies the result compiles.
Run with the conversation venv's Python, with the app stopped:

    D:\\海风\\conv-env\\Scripts\\python.exe D:\\海风\\patches\\conversation_vad\\apply.py
    D:\\海风\\conv-env\\Scripts\\python.exe D:\\海风\\patches\\conversation_vad\\apply.py --rollback
"""

import sys
import hashlib
from pathlib import Path


ORIGINAL = '                    turn_detection=ServerVad(type="server_vad", interrupt_response=True),\n'

PATCHED = '''                    turn_detection=ServerVad(
                        type="server_vad",
                        # Tunable so a noisy room cannot flush the player queue
                        # on every ambient sound. See patches/conversation_vad.
                        threshold=float(_os.getenv("REACHY_VAD_THRESHOLD", "0.85")),
                        prefix_padding_ms=int(_os.getenv("REACHY_VAD_PREFIX_PADDING_MS", "300")),
                        silence_duration_ms=int(_os.getenv("REACHY_VAD_SILENCE_MS", "900")),
                        interrupt_response=_os.getenv("REACHY_VAD_INTERRUPT", "0")
                        not in ("0", "false", "False", ""),
                    ),
'''

IMPORT_LINE = "import os as _os\n"
IMPORT_ANCHOR = "import json\n"


def target_path() -> Path:
    import reachy_mini_conversation_app

    return Path(reachy_mini_conversation_app.__file__).parent / "huggingface_realtime.py"


def main() -> int:
    """Apply or roll back the VAD patch."""
    path = target_path()
    backup = path.with_suffix(".py.orig")
    rollback = "--rollback" in sys.argv

    text = path.read_text(encoding="utf-8")

    if rollback:
        if not backup.exists():
            print("No backup found; nothing to roll back.")
            return 1
        path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Restored {path}")
        return 0

    if PATCHED in text:
        print("Already patched; nothing to do.")
        return 0

    if ORIGINAL not in text:
        print("Could not find the expected turn_detection line; no files changed.")
        print("The app version probably moved on - re-read the source before patching.")
        return 1

    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
        print(f"Backed up to {backup.name}")

    patched = text.replace(ORIGINAL, PATCHED, 1)
    if IMPORT_LINE not in patched:
        patched = patched.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    compile(patched, str(path), "exec")
    path.write_text(patched, encoding="utf-8")
    print(f"Patched {path}")
    print("sha256:", hashlib.sha256(path.read_bytes()).hexdigest())
    print()
    print("Defaults: threshold=0.85 prefix_padding=300ms silence=900ms interrupt=off")
    print("Override with REACHY_VAD_THRESHOLD / _PREFIX_PADDING_MS / _SILENCE_MS / _INTERRUPT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

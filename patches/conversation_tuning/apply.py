"""Make the conversation app's reflexes tunable for a real room.

Three upstream constants are hardcoded in ways that fight each other in a busy
space, and together they make the robot look broken:

1. Server VAD is created with no threshold at all, so ambient noise reads as
   the user starting to speak.
2. Every `input_audio_buffer.speech_started` event flushes the player queue,
   independently of `interrupt_response`. Turning interruption off upstream
   therefore does NOT stop the robot cutting itself off mid-sentence - the
   flush is client-side.
3. The idle `BreathingMove` sways the antennas +/-15 degrees at 0.5 Hz forever,
   starting 0.3 s after anything else stops. Deliberate emotions are then
   indistinguishable from the idle animation.

Each becomes an environment variable, with defaults chosen for a noisy room and
for being able to SEE when a move is intentional.

Idempotent. Keeps .orig backups and verifies each file compiles.
Run with the conversation venv's Python, with the app stopped:

    D:\\海风\\conv-env\\Scripts\\python.exe D:\\海风\\patches\\conversation_tuning\\apply.py
    D:\\海风\\conv-env\\Scripts\\python.exe D:\\海风\\patches\\conversation_tuning\\apply.py --rollback
"""

import sys
import hashlib
from typing import List, Tuple
from pathlib import Path


IMPORT_LINE = "import os as _os\n"


def _with_import(text: str) -> str:
    """Add the `os` alias above the module's first import, whatever that is."""
    if IMPORT_LINE in text:
        return text
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        # `from __future__` has to stay the first statement in the file.
        if line.startswith("from __future__"):
            continue
        if line.startswith(("import ", "from ")):
            lines.insert(index, IMPORT_LINE)
            return "".join(lines)
    raise ValueError("no import block found to anchor against")

# --- 1. server VAD parameters -------------------------------------------------

VAD_ORIGINAL = '                    turn_detection=ServerVad(type="server_vad", interrupt_response=True),\n'

VAD_PATCHED = '''                    turn_detection=ServerVad(
                        type="server_vad",
                        # Tunable: a noisy room otherwise reads as constant speech.
                        threshold=float(_os.getenv("REACHY_VAD_THRESHOLD", "0.6")),
                        prefix_padding_ms=int(_os.getenv("REACHY_VAD_PREFIX_PADDING_MS", "300")),
                        silence_duration_ms=int(_os.getenv("REACHY_VAD_SILENCE_MS", "700")),
                        interrupt_response=_os.getenv("REACHY_VAD_INTERRUPT", "0")
                        not in ("0", "false", "False", ""),
                    ),
'''

# --- 2. client-side barge-in --------------------------------------------------

BARGE_ORIGINAL = """                        if self._clear_queue:
                            self._clear_queue()
"""

BARGE_PATCHED = """                        # Upstream flushes playback on every speech_started, which in a
                        # noisy room truncates the robot's own sentence. Honour the same
                        # switch as interrupt_response so barge-in can be turned off.
                        if self._clear_queue and _os.getenv(
                            "REACHY_VAD_INTERRUPT", "0"
                        ) not in ("0", "false", "False", ""):
                            self._clear_queue()
"""

# --- 3. idle breathing amplitude ---------------------------------------------

BREATH_ORIGINAL = """        self.breathing_z_amplitude = 0.005  # 5mm gentle breathing
        self.breathing_frequency = 0.1  # Hz (6 breaths per minute)
        self.antenna_sway_amplitude = np.deg2rad(15)  # 15 degrees
        self.antenna_frequency = 0.5  # Hz (faster antenna sway)
"""

BREATH_PATCHED = """        # Tunable idle animation. The stock +/-15 deg antenna sway never stops,
        # so a deliberate emotion cannot be told apart from idling. Set
        # REACHY_BREATH_ANTENNA_DEG=0 to hold the antennas still.
        self.breathing_z_amplitude = float(_os.getenv("REACHY_BREATH_Z_MM", "3")) / 1000.0
        self.breathing_frequency = float(_os.getenv("REACHY_BREATH_HZ", "0.1"))
        self.antenna_sway_amplitude = np.deg2rad(
            float(_os.getenv("REACHY_BREATH_ANTENNA_DEG", "4"))
        )
        self.antenna_frequency = float(_os.getenv("REACHY_BREATH_ANTENNA_HZ", "0.25"))
"""


def _targets() -> List[Tuple[Path, List[Tuple[str, str]]]]:
    import reachy_mini_conversation_app

    root = Path(reachy_mini_conversation_app.__file__).parent
    return [
        (
            root / "huggingface_realtime.py",
            [(VAD_ORIGINAL, VAD_PATCHED), (BARGE_ORIGINAL, BARGE_PATCHED)],
        ),
        (root / "moves.py", [(BREATH_ORIGINAL, BREATH_PATCHED)]),
    ]


def _apply_to(path: Path, edits: List[Tuple[str, str]]) -> str:
    text = path.read_text(encoding="utf-8")
    if all(patched in text for _, patched in edits):
        return "already patched"

    missing = [original for original, patched in edits if original not in text and patched not in text]
    if missing:
        return "SKIPPED: expected source not found (app version moved on?)"

    backup = path.with_suffix(".py.orig")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")

    for original, patched in edits:
        if patched not in text:
            text = text.replace(original, patched, 1)
    text = _with_import(text)

    compile(text, str(path), "exec")
    # The alias must resolve, not just parse: a missing import only shows up at
    # runtime, as a breathing move that never starts.
    if "_os.getenv" in text and IMPORT_LINE not in text:
        raise ValueError(f"{path.name}: uses _os but the import was not added")
    path.write_text(text, encoding="utf-8")
    return "patched " + hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> int:
    """Apply or roll back every conversation tuning edit."""
    rollback = "--rollback" in sys.argv
    failures = 0

    for path, edits in _targets():
        if rollback:
            backup = path.with_suffix(".py.orig")
            if backup.exists():
                path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"{path.name}: restored")
            else:
                print(f"{path.name}: no backup, left alone")
            continue

        result = _apply_to(path, edits)
        print(f"{path.name}: {result}")
        if result.startswith("SKIPPED"):
            failures += 1

    if not rollback and not failures:
        print()
        print("Defaults:")
        print("  REACHY_VAD_THRESHOLD=0.6   REACHY_VAD_SILENCE_MS=700")
        print("  REACHY_VAD_INTERRUPT=0     (no self-interruption, no barge-in)")
        print("  REACHY_BREATH_ANTENNA_DEG=4  REACHY_BREATH_ANTENNA_HZ=0.25")
        print("  REACHY_BREATH_Z_MM=3         REACHY_BREATH_HZ=0.1")
        print("Set REACHY_BREATH_ANTENNA_DEG=0 to stop the idle antenna sway entirely.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

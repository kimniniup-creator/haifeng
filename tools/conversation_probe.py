"""Measure whether the robot can actually hold a conversation.

Service health says nothing about whether a turn completes. This speaks a
phrase into the pipeline through the gate's injection channel - the same path
microphone audio takes - then waits for a committed transcript and a spoken
reply, and reports how many rounds survived.

Run it while the conversation app is up:

    .venv\\Scripts\\python.exe tools\\conversation_probe.py --rounds 4
"""

import re
import sys
import time
import argparse
import subprocess
from typing import List, Optional, Sequence
from pathlib import Path
from datetime import datetime

ROOT = Path(r"D:\海风")
LOG = ROOT / ".runtime" / "conversation.stderr.log"
WAV = ROOT / ".runtime" / "inject.wav"
TRIGGER = ROOT / ".runtime" / "inject.trigger"
SPEAK = ROOT / "tools" / "synthesize_phrase.ps1"

STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
TRANSCRIPT = re.compile(r"role=user content=(.*)$")
REPLY = re.compile(r"role=assistant content=(.*)$")

PHRASES = [
    "What is two plus three? Answer with just the number.",
    "Say the word banana and nothing else.",
    "How many legs does a spider have? One word answer.",
    "What colour is the sky on a clear day? One word.",
    "Count from one to three out loud.",
]


def synthesize(text: str) -> bool:
    """Render the phrase to the injection WAV with Windows speech synthesis."""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(SPEAK), "-Text", text, "-Wav", str(WAV)],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
    )
    return result.returncode == 0 and WAV.exists()


def read_log() -> List[str]:
    try:
        with LOG.open("rb") as handle:
            return handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []


def watch(after: int, timeout: float) -> tuple[Optional[str], Optional[str], float]:
    """Wait for a committed transcript and a reply appearing after line *after*."""
    started = time.time()
    transcript = reply = None
    while time.time() - started < timeout:
        for line in read_log()[after:]:
            if transcript is None:
                found = TRANSCRIPT.search(line)
                if found:
                    transcript = found.group(1).strip()
            if reply is None:
                found = REPLY.search(line)
                if found:
                    reply = found.group(1).strip()
        if transcript and reply:
            break
        time.sleep(1.0)
    return transcript, reply, time.time() - started


def main(argv: Sequence[str] | None = None) -> int:
    """Run the rounds and print a pass rate."""
    parser = argparse.ArgumentParser(description="Probe real conversational turns")
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=35.0,
                        help="seconds to wait for a reply before calling the round failed")
    parser.add_argument("--gap", type=float, default=10.0, help="seconds between rounds")
    args = parser.parse_args(argv)

    passed = 0
    for index in range(args.rounds):
        phrase = PHRASES[index % len(PHRASES)]
        if not synthesize(phrase):
            print(f"round {index + 1}: could not synthesise, skipping", flush=True)
            continue

        before = len(read_log())
        TRIGGER.write_text("go", encoding="utf-8")
        print(f"[{datetime.now():%H:%M:%S}] round {index + 1}: \"{phrase}\"", flush=True)

        transcript, reply, waited = watch(before, args.timeout)
        if transcript and reply:
            passed += 1
            print(f"  heard : {transcript[:80]}")
            print(f"  replied: {reply[:80]}  ({waited:.0f}s)")
        elif transcript:
            print(f"  heard : {transcript[:80]}")
            print(f"  NO REPLY after {waited:.0f}s  <- relay LLM stage is wedged")
        else:
            print(f"  NOT HEARD after {waited:.0f}s  <- nothing reached transcription")
        time.sleep(args.gap)

    print(f"\n完整轮次 {passed}/{args.rounds}", flush=True)
    return 0 if passed == args.rounds else 1


if __name__ == "__main__":
    sys.exit(main())

"""python -m pet_interaction; no sensors, no cloud, no implicit device startup."""
import argparse
import os
import socket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--enable-devices", action="store_true")
    parser.add_argument("--voice-url", help="explicit loopback voice-owner endpoint; subscribes as pet-agent")
    args = parser.parse_args()
    from .adapters import FakeMotion, FakeVoice, HttpVoice
    from .controller import PetController
    from .service import create_app
    if args.voice_url and not args.enable_devices:
        parser.error("--voice-url requires --enable-devices (subscription changes acknowledgement ownership)")
    motion, voice = FakeMotion(), FakeVoice()
    if args.enable_devices:
        from pet_motion import MotionExecutor
        motion = MotionExecutor(dry_run=False)
        if args.voice_url:
            voice = HttpVoice(args.voice_url)
    tokens = {role: os.environ[name] for role, name in (("operator", "PET_API_TOKEN"), ("vision", "PET_VISION_TOKEN")) if os.environ.get(name)}
    app = create_app(PetController(motion=motion, voice=voice), tokens, args.voice_url)
    # Bind before adapter startup/lifespan: a second launcher cannot touch devices.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        listener.bind(("127.0.0.1", args.port))
        listener.listen(128)
        import uvicorn
        uvicorn.Server(uvicorn.Config(app, log_level="info", access_log=False)).run(sockets=[listener])
    finally:
        listener.close()


if __name__ == "__main__":
    main()

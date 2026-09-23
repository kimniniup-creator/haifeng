"""Synthetic TCP process check; no sensors, SDK, daemon, ASR or real services."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import httpx


def test_fake_process_round_trip_and_duplicate_instance_rejection(tmp_path):
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = os.environ.copy()
    env["TEMP"] = env["TMP"] = str(tmp_path)  # Separate test lease, never reserve a production lease.
    env["PET_API_TOKEN"] = secrets.token_urlsafe(32)
    env["PET_VISION_TOKEN"] = secrets.token_urlsafe(32)
    args = [sys.executable, "-m", "pet_interaction", "--port", str(port)]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(args, cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2, trust_env=False) as client:
            deadline = time.monotonic() + 12
            while True:
                try:
                    assert client.get("/health").json()["service"] == "pet-interaction"
                    break
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    assert process.poll() is None
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
            second = subprocess.run(args, cwd=root, env=env, capture_output=True, timeout=10, creationflags=flags)
            assert second.returncode != 0
            # Changing ports must not acquire a second device owner either.
            second_port = subprocess.run(args[:-1] + ["0"], cwd=root, env=env, capture_output=True, timeout=10, creationflags=flags)
            assert second_port.returncode != 0 and b"already_running" in second_port.stderr
            headers = {"Authorization": "Bearer " + env["PET_VISION_TOKEN"]}
            packet = {"schema_version":1,"source":"vision","session_id":"synthetic-camera","event_id":"frame-1",
                "kind":"wave","observed_at":time.time(),"ttl_seconds":3,"confidence":0.7,"payload":{}}
            result = client.post("/v1/events", headers=headers, json=packet).json()
            assert result["status"] == "accepted"
            deadline = time.monotonic() + 3
            while True:
                outcome = client.get("/v1/decisions/" + result["decision_id"], headers=headers).json()
                if outcome["status"] != "scheduled": break
                assert time.monotonic() < deadline
                time.sleep(0.01)
            assert outcome["motion"]["status"] == "dry_run"
            assert client.post("/v1/events", headers=headers, json=packet).json()["status"] == "duplicate"
            stop = client.post("/v1/stop", headers={"Authorization":"Bearer "+env["PET_API_TOKEN"]}).json()
            assert stop["reason"] == "stop"
            assert client.get("/v1/state", headers=headers).json()["stopped"] is True
            reply=client.post("/v1/shutdown",headers={"Authorization":"Bearer "+env["PET_API_TOKEN"]}).json()
            assert reply["scope"] == "this_pet_service_only"
            process.wait(timeout=10)
            assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)


def test_lifespan_shutdown_releases_tasks():
    from fastapi.testclient import TestClient
    from pet_interaction import PetController
    from pet_interaction.service import create_app
    controller = PetController()
    with TestClient(create_app(controller, {"operator":"x"*32})) as client:
        assert client.get("/health").status_code == 200
    assert controller.closed and controller.state == "quiet" and not controller.tasks

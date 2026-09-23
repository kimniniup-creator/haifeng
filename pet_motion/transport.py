"""REST + subscribed-before-start events. Never retry physical requests."""
import json
import asyncio
import time
from contextlib import asynccontextmanager
from urllib.parse import quote
from uuid import UUID

import httpx
from websockets.asyncio.client import connect


class DaemonError(Exception):
    def __init__(self, reason, *, uncertain=False):
        super().__init__(reason)
        self.reason = reason
        self.uncertain = uncertain


class DaemonTransport:
    def __init__(self, base_url="http://127.0.0.1:8000", *, timeout=3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @asynccontextmanager
    async def session(self):
        url = self.base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            async with connect(url + "/api/move/ws/updates", open_timeout=self.timeout,
                               close_timeout=self.timeout, proxy=None) as socket:
                yield _Session(self.base_url, client, socket)


class _Session:
    def __init__(self, base_url, client, socket):
        self.base_url, self.client, self.socket = base_url, client, socket

    async def start(self, mapping):
        if "_goto" in mapping:
            path = "/api/move/goto"
            kwargs = {"json": mapping["_goto"]}
        else:
            dataset = quote(mapping["dataset"], safe="/")
            action = quote(mapping["action_id"], safe="")
            path = f"/api/move/play/recorded-move-dataset/{dataset}/{action}"
            kwargs = {}
        try:
            response = await self.client.post(self.base_url + path, **kwargs)
        except httpx.HTTPError as exc:
            raise DaemonError("start_outcome_unknown", uncertain=True) from exc
        if response.status_code == 409:
            raise DaemonError("daemon_busy")
        if response.status_code in {400, 401, 403, 404, 422}:
            raise DaemonError(f"daemon_rejected_{response.status_code}")
        if response.status_code != 200:
            raise DaemonError(f"start_http_{response.status_code}", uncertain=True)
        try:
            return str(UUID(response.json()["uuid"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise DaemonError("invalid_start_receipt", uncertain=True) from exc

    async def wait(self, uuid):
        async for raw in self.socket:
            event = json.loads(raw)
            if event.get("uuid") != uuid:
                continue
            if event.get("type") in {"move_completed", "move_failed", "move_cancelled"}:
                return event["type"]
        raise DaemonError("event_stream_disconnected", uncertain=True)

    async def stop(self, uuid):
        response = await self.client.post(self.base_url + "/api/move/stop", json={"uuid": uuid})
        response.raise_for_status()
        # A successful stop POST is only an acknowledgement. The executor still
        # waits for the matching terminal event before permitting another move.

    async def snapshot(self):
        # Read-only preflight; never enables motors or trusts the stale ready flag.
        status = await self.client.get(self.base_url + "/api/daemon/status")
        status.raise_for_status()
        status = status.json()
        if status.get("state") != "running" or status.get("error"):
            raise DaemonError("daemon_not_running")
        if status.get("simulation_enabled") or status.get("mockup_sim_enabled"):
            raise DaemonError("simulation_not_physical")
        running = await self.client.get(self.base_url + "/api/move/running")
        running.raise_for_status()
        if running.json() != []:
            raise DaemonError("daemon_busy")
        response = await self.client.get(self.base_url + "/api/state/full", params={"use_pose_matrix": "true"})
        response.raise_for_status()
        state = response.json()
        if state.get("control_mode") != "enabled":
            raise DaemonError("motors_not_enabled")
        return state

    async def hold_current(self):
        from .micro import checked_pose
        pose = checked_pose(await self.snapshot())
        response = await self.client.post(self.base_url + "/api/move/set_target", json={
            "target_head_pose": {"m": pose["head"].reshape(-1).tolist()},
            "target_antennas": pose["antennas"].tolist(),
            "target_body_yaw": pose["body_yaw"],
        })
        response.raise_for_status()
        if response.json().get("status") != "ok":
            raise DaemonError("hold_not_applied", uncertain=True)

    async def diagnostics(self):
        # Fails closed if the maintenance-installed read-only route is absent.
        await self.snapshot()
        response = await self.client.get(self.base_url + "/api/state/motion-diagnostics")
        response.raise_for_status()
        return response.json()

    async def pin_current_joints(self):
        from .posture import diagnostic_pose
        import numpy as np
        before = diagnostic_pose(await self.diagnostics())
        joints = before["joints"]
        url = self.base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/ws/sdk"
        async with connect(url, open_timeout=2, close_timeout=1, proxy=None) as socket:
            # Native SDK commands are fire-and-forget; there is NO ack. Verify
            # actual backend target values and stable measured joints instead.
            await socket.send(json.dumps({"type":"set_head_joints", "joints":joints.tolist()}))
            until = time.monotonic() + 3
            stable_since = None
            while time.monotonic() < until:
                diag = await self.diagnostics()
                actual = diagnostic_pose(diag)
                pinned = (np.max(np.abs(actual["target_joints"]-joints)) <= 1e-6
                          and np.max(np.abs(actual["joints"]-joints)) <= .005
                          and np.max(np.abs(actual["antennas"]-before["antennas"])) <= .01
                          and diag.get("ik_required") is False)
                if pinned:
                    stable_since = time.monotonic() if stable_since is None else stable_since
                    if time.monotonic()-stable_since >= 1.0:
                        return
                else:
                    stable_since = None
                await asyncio.sleep(.05)
        raise DaemonError("joint_hold_unconfirmed", uncertain=True)

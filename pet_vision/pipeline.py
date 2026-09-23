"""Owner-supplied frames only. Does not acquire devices or persist pixels."""
from dataclasses import dataclass
from time import time
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
import json
import os


@dataclass(frozen=True)
class Frame:
    bgr: object
    observed_at: float


class Pipeline:
    def __init__(self, detector, engine, sink, clock=time):
        self.detector, self.engine, self.sink, self.clock = detector, engine, sink, clock

    def process(self, frame: Frame):
        now = self.clock()
        t = frame.observed_at
        if not (self.engine.last_timestamp < t <= now + .05 and now - t <= self.engine.max_age):
            return []
        observation = self.detector.detect(frame.bgr, t)
        events = self.engine.update(observation, now=self.clock())
        for event in events:
            self.sink(event)
        return events


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalEventSink:
    def __init__(self, url="http://127.0.0.1:8091/v1/events", token=None):
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1", "localhost") or parsed.username or parsed.password:
            raise ValueError("Vision events may only go to a local HTTP backend")
        self.url = url
        self.token = token if token is not None else os.environ.get("PET_API_TOKEN")
        if not self.token:
            raise ValueError("PET_API_TOKEN is required for event delivery")
        self.opener = build_opener(ProxyHandler({}), NoRedirect)

    def __call__(self, event):
        req = Request(self.url, json.dumps(event, allow_nan=False).encode(),
                      {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"})
        # No retry queue: a delayed gesture must never replay as a fresh command.
        with self.opener.open(req, timeout=.5) as response:
            return json.load(response)

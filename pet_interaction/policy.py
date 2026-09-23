"""Small transparent language policy; no remote inference or transcript rewrite."""
import json
from pathlib import Path
import re


class RulePolicy:
    def __init__(self, path=None):
        self.rules = json.loads(Path(path or Path(__file__).with_name("rules.json")).read_text(encoding="utf-8"))

    def classify(self, text):
        candidate = re.sub(r"[\s，。！？、,.!?]", "", text)
        named = False
        for alias in self.rules["name_aliases"]:
            if candidate.startswith(alias):
                named, candidate = True, candidate[len(alias):]
                break
        if named and not candidate:
            return "wake", "attention", "curious"
        for intent, phrases in self.rules["commands"].items():
            if candidate in phrases:
                return {"greeting": (intent, "greeting", "happy"),
                        "attention": (intent, "attention", "curious"),
                        "wake": (intent, "attention", "curious"),
                        "stop": (intent, "stop", None),
                        "quiet": (intent, "quiet", None),
                        "rest": (intent, "rest", None)}[intent]
        return "unknown", "quiet", "uncertain"

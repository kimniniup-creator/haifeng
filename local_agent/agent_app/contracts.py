from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Observation(Strict):
    summary: str
    visible_objects: list[str]
    readable_text: list[str]
    uncertainties: list[str]
    image_quality: Literal['usable', 'limited', 'unusable']
    answer: str
    needs_better_image: bool
    response_emotion: Literal['none', 'joy', 'excitement', 'sadness', 'anger', 'confusion', 'curiosity'] = 'none'
    emotion_evidence: str = ''

class Inspect(Strict):
    image_id: str
    question: str

class Search(Strict):
    query: str
    limit: int

class Remember(Strict):
    text: str
    evidence_ids: list[str]
    kind: Literal['user_statement', 'shared_observation']

class Respond(Strict):
    text: str
    # New emotion names are the public Agent contract. The legacy values remain
    # accepted so stored jobs and older clients can be replayed safely.
    expression: Literal[
        'none', 'joy', 'excitement', 'sadness', 'anger', 'confusion', 'curiosity',
        'nod', 'curious', 'greeting'
    ]
    delivery: Literal['robot_and_text', 'text_only']

class Quiet(Strict):
    enabled: bool

TOOL_MODELS = {
    'inspect_image': (Inspect, 'Reinspect an existing image to answer a specific detail. Does not capture.'),
    'search_memory': (Search, 'Retrieve shared experiences. Return evidence and time. limit 1 to 5.'),
    'remember_event': (Remember, 'Save a supported memory with existing evidence IDs.'),
    'respond': (Respond, 'Respond once per turn, after necessary memory/inspection tools. Text max 160 Chinese characters. Robot delivery expresses with voice and motion.'),
    'set_quiet_mode': (Quiet, 'Set the session quiet mode.'),
}

def tool_specs(allow_respond=True):
    return [
        {'type': 'function', 'function': {
            'name': name, 'description': description, 'strict': True,
            'parameters': cls.model_json_schema(),
        }}
        for name, (cls, description) in TOOL_MODELS.items()
        if allow_respond or name != 'respond'
    ]

class JobRequest(Strict):
    session_id: str
    request_id: str = Field(min_length=1, max_length=100)
    kind: Literal['capture', 'message', 'image']
    text: str = Field(default='', max_length=2000)
    image_id: str | None = None

class ModeRequest(Strict):
    quiet: bool

class MemoryEdit(Strict):
    text: str = Field(min_length=1, max_length=1000)

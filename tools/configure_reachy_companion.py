"""Apply non-secret Chinese companion settings to the installed official app."""
import json
from pathlib import Path
import importlib.util

spec=importlib.util.find_spec('reachy_mini_conversation_app')
if spec is None or not spec.origin: raise SystemExit('Install official conversation app first')
instance=Path(spec.origin).parent
source=Path(__file__).resolve().parents[1]/'config/conversation/haifeng/profile.md'
target=instance/'user_personalities/haifeng/profile.md'
target.parent.mkdir(parents=True,exist_ok=True)
source_text=source.read_text(encoding='utf-8-sig')
if target.exists() and target.read_text(encoding='utf-8-sig')!=source_text:
    raise SystemExit('Existing customized Haifeng profile differs; refusing overwrite')
target.write_text(source_text,encoding='utf-8')
settings=instance/'startup_settings.json'
desired={'profile':'user_personalities/haifeng','voice':'Vivian'}
if settings.exists():
    current=json.loads(settings.read_text(encoding='utf-8-sig'))
    if any(current.get(key)!=value for key,value in desired.items()):
        raise SystemExit('Different startup settings exist; choose profile in app instead')
else:
    settings.write_text(json.dumps(desired,ensure_ascii=False,indent=2),encoding='utf-8')
env=instance/'.env'
if not env.exists():
    env.write_text('REALTIME_TRANSCRIPTION_LANGUAGE=zh\nHF_REALTIME_CONNECTION_MODE=deployed\n',encoding='utf-8')
else:
    print('Existing instance environment preserved; select Chinese in settings if necessary')
from reachy_mini_conversation_app.profile_store import read_profile
from reachy_mini_conversation_app.config import set_instance_path
set_instance_path(instance)
profile=read_profile('user_personalities/haifeng')
assert profile.voice=='Vivian' and '普通话' in profile.instructions
print('Chinese companion profile validated and saved:',target)

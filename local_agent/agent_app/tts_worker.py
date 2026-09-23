"""One request per process: isolates Windows COM/SAPI and permits cancellation."""
import json
import sys
from pathlib import Path

def main():
    import pyttsx3
    engine = pyttsx3.init('sapi5')
    voices = engine.getProperty('voices')
    if '--list' in sys.argv:
        print(json.dumps([{'id': v.id, 'name': v.name, 'languages': str(v.languages)} for v in voices], ensure_ascii=True))
        return
    request = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    voice_id = request.get('voice')
    if voice_id and voice_id not in {v.id for v in voices}:
        raise RuntimeError('CONFIGURED_VOICE_NOT_AVAILABLE')
    if not voice_id:
        voice = next((v for v in voices if any(k in (v.name + ' ' + v.id).lower()
            for k in ('chinese', 'zh-cn', 'zh-tw', 'huihui', 'kangkang', 'yaoyao'))), None)
        if voice is None:
            raise RuntimeError('NO_CHINESE_SAPI_VOICE: run python -m agent_app.tts_worker --list')
        voice_id = voice.id
    engine.setProperty('voice', voice_id)
    engine.setProperty('rate', int(request.get('rate', 170)))
    engine.setProperty('volume', 0.8)
    output = Path(request['output'])
    tmp = output.with_name(output.stem + '.part.wav')
    try:
        engine.save_to_file(request['text'], str(tmp))
        engine.runAndWait()
        engine.stop()
        tmp.replace(output)
    finally:
        tmp.unlink(missing_ok=True)

if __name__ == '__main__':
    main()

"""Offline-only phrase research. Never imports a device, server or robot SDK."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'patches/reachy_companion/pet_audio.py'
spec = importlib.util.spec_from_file_location('baseline_pet_audio', SOURCE)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
RATE = baseline.RATE
# Read the existing literal inventory, fail rather than invent units after drift.
function = next(n for n in ast.parse(SOURCE.read_text(encoding='utf-8')).body
                if isinstance(n, ast.FunctionDef) and n.name == 'mechanical_voice')
NOTES = ast.literal_eval(next(n.value for n in function.body
                            if isinstance(n, ast.Assign) and any(
                                isinstance(t, ast.Name) and t.id == 'notes' for t in n.targets)))


def render(plan):
    """Pure float32 mono PCM. Proposed v1 format, NOT a production API."""
    if plan['version'] != 1 or plan['semantic_id'] not in baseline.KINDS:
        raise ValueError('Unknown version or semantic')
    if plan['intent'] in ('stop', 'quiet', 'interrupted'):
        if plan['units'] or plan['total_duration_ms'] != 0:
            raise ValueError('Cancellation must be silent')
        return np.zeros(0, np.float32)
    if not 1 <= len(plan['units']) <= 12:
        raise ValueError('Bounded phrase required')
    rng = np.random.default_rng(plan['variant_seed'])
    pieces = []
    for unit in plan['units']:
        kind, index = unit['motif_id'].split(':')
        if kind not in NOTES or not index.isdecimal() or int(index) >= len(NOTES[kind]):
            raise ValueError('Unknown source unit')
        f0, f1, duration = NOTES[kind][int(index)]
        scale, stretch, gain, gap = (unit[k] for k in
                                     ('pitch_scale', 'duration_scale', 'intensity', 'gap_ms'))
        curve = np.asarray(unit['pitch_curve_st'], dtype=float)
        if not (.8 <= scale <= 1.2 and .65 <= stretch <= 2.1 and
                .4 <= gain <= 1.1 and 0 <= gap <= 250 and
                curve.shape == (3,) and np.isfinite(curve).all() and abs(curve).max() <= 3):
            raise ValueError('Prosody outside research bounds')
        duration *= stretch
        n = round(RATE * duration)
        t = np.arange(n) / RATE
        pitch = (f0 + (f1-f0)*t/duration) * scale
        pitch *= 2 ** (np.interp(np.linspace(0, 1, n), [0, .5, 1], curve)/12)
        # Integrate instantaneous frequency; preserve original FM/timbre constants.
        phase = 2*np.pi * np.concatenate(([0.], np.cumsum((pitch[:-1]+pitch[1:])/2)/RATE))
        envelope = np.maximum(0, np.sin(np.pi*np.arange(n)/max(1, n-1))) ** 1.5
        tone = .11*np.sin(phase+.45*np.sin(2*np.pi*37*t)) + .018*np.sin(2*phase)
        pcm = gain * envelope * (tone+rng.normal(0, .004, n))
        pieces.extend((pcm.astype(np.float32), np.zeros(round(RATE*gap/1000), np.float32)))
    pcm = np.concatenate(pieces)
    if abs(len(pcm)/RATE*1000-plan['total_duration_ms']) > 1 or len(pcm) > RATE*1.8:
        raise ValueError('Duration mismatch or over budget')
    if not np.isfinite(pcm).all() or np.max(np.abs(pcm)) > .16:
        raise ValueError('Unsafe PCM peak')
    return pcm


def write_wav(path, pcm):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes((pcm*32767).astype('<i2').tobytes())


def main():
    out = ROOT / 'qa-artifacts/jiujiu-language'
    out.mkdir(parents=True, exist_ok=True)
    plans = json.loads((ROOT/'research/jiujiu-language/phrases.json').read_text(encoding='utf-8'))
    report = {'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'files': []}
    for name, pcm in [(f'old_{k}', baseline.mechanical_voice(k)) for k in baseline.KINDS] + [
            (p['candidate_id'], render(p)) for p in plans]:
        if not len(pcm):
            continue  # Cancellation is no sound, never an empty file queued to playback.
        path = out/f'{name}.wav'
        write_wav(path, pcm)
        report['files'].append({'file': path.name, 'duration_ms': len(pcm)*1000/RATE,
                                'peak': float(abs(pcm).max()),
                                'rms': float(np.sqrt(np.mean(pcm**2))),
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    # Demonstrate real existing gate cancellation, not a new 'interrupted' utterance.
    p = next(p for p in plans if p['candidate_id'] == 'moon')
    clock = [0.]
    gate = baseline.TurnGate(clock=lambda: clock[0])
    gate.enqueue(gate.advance('offline_demo'), 'offline', render(p), 2.5)
    blocks = []
    for i in range(60):
        clock[0] = i*.02
        if i == 21:
            gate.advance('new_speech')
        block = np.empty((320, 1), np.float32)
        gate.render(block)
        blocks.append(block[:, 0].copy())
    pcm = np.concatenate(blocks)
    assert not pcm[21*320:].any()
    write_wav(out/'interrupted.wav', pcm)
    report['interrupted'] = {'cut_ms': 420, 'silence_after_cut_verified': True}
    (out/'measurements.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    listening = ['# 啾啾语离线试听（P2，未部署）', '',
                 '点击播放器自行试听。本轮未做实体播放或主观听感验收。', '']
    names = {'name': '叫名字', 'moon': '看月亮', 'happy': '开心', 'curious': '好奇',
             'uncertain': '没听懂', 'thinking': '思考', 'sleepy': '困倦', 'interrupted': '被打断'}
    for plan in plans:
        name = plan['candidate_id']
        if name not in names:
            continue
        old = 'curious' if name == 'interrupted' else plan['semantic_id']
        listening.extend([f'## {names[name]}', '',
                          f'![候选]({(out / (name + ".wav")).as_posix()})', '',
                          f'![旧版]({(out / ("old_" + old + ".wav")).as_posix()})', ''])
    (out/'LISTEN.md').write_text('\n'.join(listening), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

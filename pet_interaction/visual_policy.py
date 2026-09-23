"""Visible-cue rules, not emotional-state inference. Phase one is smile only."""
import math


VISUAL_KINDS = {"visual_cue", "face_presence", "visual_unknown"}


def smile_sound(event):
    """Return a mechanical sound only for the producer's bounded stable smile rule."""
    if event.kind != 'visual_cue':
        return None, 'observation_only'
    p = event.payload
    if p.get('cue_name') != 'smile':
        return None, 'cue_not_enabled'
    if event.ttl_seconds > 2 or event.confidence < .7:
        return None, 'invalid_cue_freshness_or_confidence'
    if p.get('confidence_basis') != 'configured_detection_floor':
        return None, 'unsupported_confidence_basis'
    if type(p.get('face_count')) is not int or p['face_count'] != 1 or p.get('attribution') != 'single_face':
        return None, 'ambiguous_face'
    quality = p.get('quality')
    if not isinstance(quality, dict) or quality.get('usable') is not True or quality.get('reasons') != []:
        return None, 'face_quality_unknown'
    stable = p.get('stable_ms')
    if type(stable) not in (int, float) or not math.isfinite(stable) or stable < 800:
        return None, 'cue_not_stable'
    track = p.get('track_id')
    if not isinstance(track, str) or not 1 <= len(track) <= 128:
        return None, 'missing_temporary_track'
    basis = p.get('rule_basis')
    if not isinstance(basis, dict) or basis.get('version') != 'face-cues-v1':
        return None, 'unsupported_rule'
    coefficients = basis.get('coefficients')
    if not isinstance(coefficients, dict):
        return None, 'missing_visible_evidence'
    for key in ('mouthSmileLeft', 'mouthSmileRight'):
        value = coefficients.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not .55 <= value <= 1:
            return None, 'smile_below_threshold'
    if p.get('interpretation') != 'visible_facial_cue' or p.get('provisional') is not False:
        return None, 'cue_not_confirmed'
    return 'happy', None

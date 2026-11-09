from fractions import Fraction

from .calibration import CalibrationProfile, check_profile, corrected_time, zero_profile
from .models import (Photo, PhotoPlacement, PhotoTiming, Sound, SoundPlacement, Timeline,
                     Video, VideoPlacement)


def build_timeline(videos: list[Video], photos: list[Photo], *,
                   tolerance: Fraction = Fraction(0), mode: str = "until_next",
                   fixed_duration: Fraction = Fraction(3), sound: Sound | None = None,
                   fps: Fraction = Fraction(30), name: str = "FujiTimeline",
                   profile: CalibrationProfile | None = None) -> Timeline:
    profile = profile or zero_profile()
    check_profile(profile)
    if not 0 <= tolerance <= 60:
        raise ValueError("A tolerância deve estar entre 0 e 60 segundos.")
    if mode not in {"until_next", "fixed"}:
        raise ValueError("Modo desconhecido; use until_next ou fixed.")
    if fixed_duration <= 0 or fps <= 0:
        raise ValueError("Duração fixa e FPS devem ser positivos.")
    if not videos or any(v.duration <= 0 for v in videos):
        raise ValueError("É necessário pelo menos um vídeo com duração positiva.")
    if sound and sound.duration <= 0:
        raise ValueError("O WAV precisa ter duração positiva.")
    ordered = sorted(videos, key=lambda v: (v.captured.utc, str(v.path)))
    placements, cursor = [], Fraction(0)
    for video in ordered:
        placements.append(VideoPlacement(video, cursor))
        cursor += video.duration
    result = Timeline(name, placements, [], [], cursor)
    result.calibration = profile
    if profile.status != "uncalibrated":
        result.warnings.append(f"Perfil {profile.name} ({profile.pair_id}): offset {profile.offset_seconds}s, status {profile.status}.")
    if profile.validation and profile.validation.reasons:
        result.warnings.extend(profile.validation.reasons)
    candidates = []
    for photo in sorted(photos, key=lambda p: (p.captured.utc, str(p.path))):
        # Correction is applied BEFORE coverage selection, retaining original EXIF.
        corrected = photo.captured.utc + profile.offset_seconds
        matches = []
        for i, placed in enumerate(placements):
            relative = corrected - placed.media.captured.utc
            duration = placed.media.duration
            inside = 0 <= relative < duration
            distance = max(-relative, relative - duration, Fraction(0))
            if inside or (tolerance > 0 and distance <= tolerance):
                matches.append((not inside, distance, i, relative))
        result.photo_timings.append(PhotoTiming(photo.path, photo.captured, corrected,
                                               corrected_time(photo.captured, profile.offset_seconds),
                                               profile.name, profile.offset_seconds, profile.status, bool(matches)))
        if not matches:
            result.excluded.append(photo.path)
            continue
        _, _, i, relative = min(matches)
        video = placements[i]
        # Outside coverage but within tolerance: anchor to the nearest visible edge.
        local = max(Fraction(0), relative)
        if local >= video.media.duration:
            local = max(Fraction(0), video.media.duration - 1 / fps)
        clamped = local != relative
        if clamped:
            result.warnings.append(f"{photo.path.name}: tolerância usada; posição limitada à borda do vídeo.")
        if sum(not m[0] for m in matches) > 1:
            result.warnings.append(f"{photo.path.name}: vídeos sobrepostos; escolhido o primeiro cronológico.")
        candidates.append((video.offset + local, photo, i, relative, clamped))
    candidates.sort(key=lambda item: (item[0], str(item[1].path)))
    for n, (offset, photo, i, relative, clamped) in enumerate(candidates):
        next_offset = candidates[n + 1][0] if n + 1 < len(candidates) else cursor
        if next_offset <= offset:
            raise ValueError(f"Fotos no mesmo instante da timeline: {photo.path.name}; selecione uma delas.")
        duration = next_offset - offset
        if mode == "fixed":
            duration = min(duration, fixed_duration)
        result.photos.append(PhotoPlacement(photo, i, relative, offset, duration, clamped))
        if sound:
            # Keep each repetition in a single independent lane, cutting before the next shutter.
            result.sounds.append(SoundPlacement(sound, offset, min(sound.duration, next_offset - offset)))
    for media in [*ordered, *photos]:
        if media.captured.assumed_timezone:
            result.warnings.append(f"{media.path.name}: fuso informado pelo usuário: {media.captured.assumed_timezone}.")
    return result

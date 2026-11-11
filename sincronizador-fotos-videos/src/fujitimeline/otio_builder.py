"""Build editable tracks and quantize only the export copy to the project grid."""

from fractions import Fraction

import opentimelineio as otio

from .models import Timeline
from .temporal import floor_frame, nearest_frame

SUPPORTED_FPS = {Fraction(x) for x in ("24", "25", "30", "50", "60", "24000/1001", "30000/1001", "60000/1001")}


def build_otio(plan: Timeline, fps: Fraction = Fraction(30)) -> tuple[otio.schema.Timeline, list[str]]:
    if fps not in SUPPORTED_FPS:
        raise ValueError("FPS de projeto não suportado; use 24, 25, 30, 50, 60 ou as taxas NTSC racionais.")
    notes = []
    rt = lambda seconds: otio.opentime.RationalTime(float(seconds * fps), float(fps))
    tr = lambda start, duration: otio.opentime.TimeRange(rt(start), rt(duration))
    timeline = otio.schema.Timeline(name=plan.name)
    videos = otio.schema.Track(name="Vídeos", kind=otio.schema.TrackKind.Video)
    photos = otio.schema.Track(name="Fotografias", kind=otio.schema.TrackKind.Video)
    sounds = otio.schema.Track(name="Disparos", kind=otio.schema.TrackKind.Audio)
    timeline.tracks.extend([videos, photos, sounds])
    frame_starts, frame_lengths = [], []
    cursor = 0
    for item in plan.videos:
        count = floor_frame(item.media.duration, fps)
        if count < 1:
            raise ValueError(f"Vídeo menor que um quadro de projeto: {item.media.path}")
        frame_starts.append(cursor)
        frame_lengths.append(count)
        if count / fps != item.media.duration:
            notes.append(f"{item.media.path.name}: cauda inferior a um quadro omitida da edição ({item.media.duration - count / fps}s).")
        cursor += count

    def clip(media, kind, start, duration, source_start=Fraction(0)):
        asset_duration = Fraction(0) if kind == "photo" else media.duration
        reference = otio.schema.ExternalReference(
            target_url=media.path.resolve().as_uri(),
            available_range=tr(source_start, max(duration, asset_duration)),
        )
        reference.metadata["fuji"] = {
            "kind": kind, "duration": str(asset_duration), "source_start": str(source_start),
            "width": getattr(media, "width", 0), "height": getattr(media, "height", 0),
            "fps": str(getattr(media, "fps", fps)),
            "channels": getattr(media, "audio_channels", getattr(media, "channels", 0)),
            "sample_rate": getattr(media, "audio_rate", getattr(media, "sample_rate", 48000)),
        }
        item = otio.schema.Clip(name=media.path.name, media_reference=reference,
                                source_range=tr(source_start, duration))
        item.metadata["fuji"] = {"offset": str(start), "duration": str(duration)}
        return item

    for i, item in enumerate(plan.videos):
        videos.append(clip(item.media, "video", frame_starts[i] / fps,
                           frame_lengths[i] / fps, item.media.source_start))

    def map_end(seconds):
        if seconds >= plan.duration:
            return cursor
        for i, item in enumerate(plan.videos):
            if seconds < item.offset + item.media.duration:
                return frame_starts[i] + min(frame_lengths[i], nearest_frame(seconds - item.offset, fps))
        raise ValueError("Posição fora da timeline.")

    starts = []
    for item in plan.photos:
        i = item.video_index
        local = item.offset - plan.videos[i].offset
        start = frame_starts[i] + min(frame_lengths[i] - 1, nearest_frame(local, fps))
        starts.append(start)
        if start / fps != item.offset:
            notes.append(f"{item.media.path.name}: posição exportada {start / fps}s (metadados na timeline: {item.offset}s).")
    if any(b <= a for a, b in zip(starts, starts[1:])):
        raise ValueError("Duas fotos ocupam o mesmo quadro; aumente --fps ou selecione menos fotos.")
    photo_cursor, sound_cursor = Fraction(0), Fraction(0)
    for n, item in enumerate(plan.photos):
        start = starts[n] / fps
        next_start = starts[n + 1] / fps if n + 1 < len(starts) else cursor / fps
        end = min(map_end(item.offset + item.duration) / fps, next_start)
        if end <= start:
            raise ValueError(f"Duração da foto menor que um quadro após arredondamento: {item.media.path}")
        if start > photo_cursor:
            photos.append(otio.schema.Gap(source_range=tr(Fraction(0), start - photo_cursor)))
        photos.append(clip(item.media, "photo", start, end - start))
        photo_cursor = end
        if plan.sounds:
            effect = plan.sounds[n]
            length = min(effect.duration, next_start - start, cursor / fps - start)
            if start > sound_cursor:
                sounds.append(otio.schema.Gap(source_range=tr(Fraction(0), start - sound_cursor)))
            sounds.append(clip(effect.media, "sound", start, length))
            sound_cursor = start + length
    return timeline, notes

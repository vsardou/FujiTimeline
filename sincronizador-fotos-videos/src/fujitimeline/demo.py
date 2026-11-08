"""Synthetic metadata only. The referenced paths deliberately contain no media."""

from pathlib import Path

from .metadata import photo_from_exif, video_from_probe
from .timeline import build_timeline


def demo_timeline(**options):
    root = Path("example-media").resolve()
    video = video_from_probe(root / "video-24.398.mov", {
        "format": {"tags": {"com.apple.quicktime.creationdate": "2026-11-06T12:00:00.000-03:00"}},
        "streams": [{"codec_type": "video", "width": 1080, "height": 1920,
                     "avg_frame_rate": "30/1", "duration_ts": 24398, "time_base": "1/1000"}],
    })
    times = ["12.660", "16.880", "19.830", "23.420"]
    photos = [photo_from_exif(root / f"photo-{i + 1}.jpg", {
        "EXIF:DateTimeOriginal": f"2026:11:06 12:00:{value[:2]}",
        "EXIF:SubSecTimeOriginal": value.split(".")[1],
        "EXIF:OffsetTimeOriginal": "-03:00", "File:ImageWidth": 7728, "File:ImageHeight": 5152,
    }) for i, value in enumerate(times)]
    return build_timeline([video], photos, **options)

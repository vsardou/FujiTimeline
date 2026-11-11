from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .calibration import CalibrationProfile


@dataclass(frozen=True)
class CaptureTime:
    """Exact UTC epoch seconds plus the original timestamp and offset provenance."""

    utc: Fraction
    raw: str
    source: str
    offset: str
    assumed_timezone: str | None = None


@dataclass(frozen=True)
class Video:
    path: Path
    captured: CaptureTime
    duration: Fraction
    width: int = 1920
    height: int = 1080
    fps: Fraction = Fraction(30)
    audio_channels: int = 0
    audio_rate: int = 48000
    source_start: Fraction = Fraction(0)


@dataclass(frozen=True)
class Photo:
    path: Path
    captured: CaptureTime
    width: int = 6000
    height: int = 4000


@dataclass(frozen=True)
class Sound:
    path: Path
    duration: Fraction
    channels: int = 2
    sample_rate: int = 48000


@dataclass(frozen=True)
class VideoPlacement:
    media: Video
    offset: Fraction


@dataclass(frozen=True)
class PhotoPlacement:
    media: Photo
    video_index: int
    source_offset: Fraction
    offset: Fraction
    duration: Fraction
    clamped: bool = False


@dataclass(frozen=True)
class SoundPlacement:
    media: Sound
    offset: Fraction
    duration: Fraction


@dataclass(frozen=True)
class PhotoTiming:
    path: Path
    original: CaptureTime
    corrected_utc: Fraction
    corrected_time: str
    profile_name: str
    offset_seconds: Fraction
    status: str
    selected: bool


@dataclass
class Timeline:
    name: str
    videos: list[VideoPlacement]
    photos: list[PhotoPlacement]
    sounds: list[SoundPlacement]
    duration: Fraction
    excluded: list[Path] = field(default_factory=list)
    manually_excluded: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    calibration: CalibrationProfile | None = None
    photo_timings: list[PhotoTiming] = field(default_factory=list)
    skipped_missing_capture_time: list[Path] = field(default_factory=list)

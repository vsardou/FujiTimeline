"""Desktop workflow, independent of Tk widgets and preserving original media."""
from dataclasses import dataclass, replace
from collections import OrderedDict
from fractions import Fraction
from pathlib import Path
import os
import re
import shutil
import sys

from .calibration import CalibrationProfile, zero_profile
from .metadata import MetadataReader, record_missing_dates
from .selection import select_files
from .timeline import build_timeline
from .export_fcpxml import export_fcpxml
from .report import to_json, write_new
from .jobs import check_cancel


def seconds(text: str) -> Fraction:
    """Accept signed seconds or MM:SS / HH:MM:SS, comma or decimal point."""
    value = text.strip().replace(',', '.')
    if not re.fullmatch(r'[+-]?\d+(?::\d+){0,2}(?:\.\d+)?', value):
        raise ValueError('Use segundos (−2,202 digitado como -2,202) ou -00:02,202.')
    sign = -1 if value.startswith('-') else 1
    parts = value.lstrip('+-').split(':')
    if len(parts) > 1 and any(Fraction(p) >= 60 for p in parts[1:]):
        raise ValueError('Segundos e minutos internos devem ser menores que 60.')
    result = Fraction(0)
    for part in parts:
        result = result * 60 + Fraction(part)
    return sign * result


def manual_profile(offset: str, pair: str) -> CalibrationProfile:
    value = seconds(offset)
    if not value:
        return zero_profile(pair.strip() or None)
    if not pair.strip():
        raise ValueError('Informe um nome para o par câmera/iPhone ao usar correção.')
    return CalibrationProfile('Correção manual', pair.strip(), value, 'experimental')


def find_tool(name: str) -> str:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) / "tools"
        bundled = base / ("exiftool/exiftool" if name == "exiftool" else name)
        if bundled.is_file():
            return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    candidates = [local / 'Programs' / 'ExifTool' / 'exiftool.exe'] if name == 'exiftool' else list(
        (local / 'Microsoft' / 'WinGet' / 'Packages').glob('Gyan.FFmpeg*/**/ffprobe.exe'))
    candidates += [Path('/opt/homebrew/bin') / name, Path('/usr/local/bin') / name]
    return next((str(p) for p in candidates if p.is_file()), name)


@dataclass(frozen=True)
class Request:
    videos: tuple[Path, ...]
    photos: Path
    profile: CalibrationProfile
    output: Path
    mode: str = 'until_next'
    fixed: Fraction = Fraction(3)
    tolerance: Fraction = Fraction(0)
    fps: Fraction = Fraction(30)
    recursive: bool = False
    sound: Path | None = None
    timezone: str | None = None
    ffprobe: str = 'ffprobe'
    exiftool: str = 'exiftool'
    unchecked: frozenset[Path] = frozenset()
    target: str = "final-cut"


def execute(request: Request, export: bool = False):
    if not 0 <= request.tolerance <= 60:
        raise ValueError('A tolerância deve estar entre 0 e 60 segundos.')
    report = request.output.with_suffix('.json')
    if export and (request.output.suffix.lower() != '.fcpxml' or request.output.exists() or report.exists()):
        raise ValueError('Escolha um destino .fcpxml novo. XML e relatório existentes não serão sobrescritos.')
    inputs = select_files(list(request.videos), request.photos, request.sound, request.recursive)
    reader = MetadataReader(request.ffprobe, request.exiftool, request.timezone)
    plan = build_timeline([reader.video(p) for p in inputs.videos], reader.photos(inputs.photos),
                          profile=request.profile, tolerance=request.tolerance, mode=request.mode,
                          fixed_duration=request.fixed, fps=request.fps,
                          sound=reader.sound(inputs.sound) if inputs.sound else None)
    record_missing_dates(plan, reader.skipped_missing_capture_time)
    if export:
        plan.warnings.extend(export_fcpxml(plan, request.output, fps=request.fps, target=request.target))
        write_new(report, to_json(plan), '.json')
    return plan


@dataclass
class Review:
    plan: object
    candidates: object


class Session:
    """One worker owns the bounded metadata cache. No persistent private metadata."""
    def __init__(self):
        self.cache = OrderedDict()

    def run(self, request, export=False, cancel=None, progress=lambda *args: None):
        check_cancel(cancel)
        if not 0 <= request.tolerance <= 60:
            raise ValueError('A tolerância deve estar entre 0 e 60 segundos.')
        report = request.output.with_suffix('.json')
        if export and (request.output.suffix.lower() != '.fcpxml' or request.output.exists() or report.exists()):
            raise ValueError('Escolha um destino .fcpxml novo; XML/JSON existentes não serão sobrescritos.')
        progress(0, 1, 'Buscando JPEGs na pasta…')
        inputs = select_files(list(request.videos), request.photos, request.sound, request.recursive, cancel)
        reader = MetadataReader(request.ffprobe, request.exiftool, request.timezone, cancel)
        total = len(inputs.videos) + len(inputs.photos) + bool(inputs.sound)
        count = 0
        def read(path, kind):
            nonlocal count
            check_cancel(cancel)
            stat = path.stat()
            key = (path, stat.st_size, stat.st_mtime_ns, kind, request.timezone, request.ffprobe, request.exiftool)
            if key not in self.cache:
                self.cache[key] = next(iter(reader.photos((path,))), None) if kind == 'photo' else getattr(reader, kind)(path)
            self.cache.move_to_end(key)
            value = self.cache[key]
            while len(self.cache) > 10000:
                self.cache.popitem(last=False)
            count += 1
            progress(count, total, f'{count}/{total} • {path.name}')
            return value
        videos = [read(p, 'video') for p in inputs.videos]
        photos, skipped = [], []
        for path in inputs.photos:
            photo = read(path, 'photo')
            if photo is None:
                skipped.append(path)
            else:
                photos.append(photo)
        sound = read(inputs.sound, 'sound') if inputs.sound else None
        options = dict(profile=request.profile, tolerance=request.tolerance, mode=request.mode,
                       fixed_duration=request.fixed, fps=request.fps, sound=sound)
        check_cancel(cancel)
        candidates = build_timeline(videos, photos, **options)
        plan = build_timeline(videos, [p for p in photos if p.path not in request.unchecked], **options)
        record_missing_dates(candidates, skipped)
        record_missing_dates(plan, skipped)
        plan.manually_excluded = [p.path for p in photos if p.path in request.unchecked]
        # Preserve audit data even for manually excluded photos.
        selected = {p.media.path for p in plan.photos}
        plan.photo_timings = [replace(t, selected=t.path in selected) for t in candidates.photo_timings]
        check_cancel(cancel)
        if export:
            progress(total, total, 'Gravando XML e relatório…')
            # Once writing starts, finish both small outputs; cancellation never truncates them.
            plan.warnings.extend(export_fcpxml(plan, request.output, fps=request.fps, target=request.target))
            write_new(report, to_json(plan), '.json')
        return Review(plan, candidates)


def thumbnail(path: Path):
    """Read a reduced JPEG preview in memory only; never save to source media."""
    from PIL import Image, ImageOps
    with Image.open(path) as image:
        image.draft('RGB', (160, 120))
        image = ImageOps.exif_transpose(image)
        image.thumbnail((72, 52))
        return image.convert('RGB').copy()

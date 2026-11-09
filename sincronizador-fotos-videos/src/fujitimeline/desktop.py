"""Desktop workflow, independent of Tk widgets and preserving original media."""
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import os
import re
import shutil

from .calibration import CalibrationProfile, zero_profile
from .metadata import MetadataReader
from .selection import select_files
from .timeline import build_timeline
from .export_fcpxml import export_fcpxml
from .report import to_json, write_new


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
    if export:
        plan.warnings.extend(export_fcpxml(plan, request.output, fps=request.fps))
        write_new(report, to_json(plan), '.json')
    return plan

"""Read-only subprocess adapters. Never use filesystem dates as capture dates."""

import json
import re
import os
import subprocess
import time
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from .models import Photo, Sound, Video
from .temporal import parse_timestamp
from .jobs import check_cancel


class MissingPhotoCaptureTime(ValueError):
    """A JPEG without a capture date is not a synchronization candidate."""


def record_missing_dates(plan, paths):
    plan.skipped_missing_capture_time = list(paths)
    plan.warnings.extend(f'{path.name}: ignorada; sem data/hora de captura EXIF.' for path in paths)


def run_json(command: list[str], cancel=None):
    try:
        if cancel is None:
            completed = subprocess.run(command, check=True, capture_output=True,
                                   encoding="utf-8", errors="replace", timeout=120,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        else:
            check_cancel(cancel)
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  encoding='utf-8', errors='replace',
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as process:
                deadline = time.monotonic() + 120
                try:
                    while True:
                        check_cancel(cancel)
                        if time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(command, 120)
                        try:
                            out, err = process.communicate(timeout=.1)
                            break
                        except subprocess.TimeoutExpired:
                            continue
                    if process.returncode:
                        raise subprocess.CalledProcessError(process.returncode, command, out, err)
                    completed = subprocess.CompletedProcess(command, 0, out, err)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
    except FileNotFoundError as exc:
        raise ValueError(f"Ferramenta não encontrada: {command[0]}. Instale-a ou informe seu caminho.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Tempo limite ao ler metadados com {command[0]}.") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Falha ao ler metadados: {exc.stderr.strip()}") from exc
    try:
        return json.loads(completed.stdout, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Resposta JSON inválida de {command[0]}.") from exc


def probe(path: Path, executable: str = "ffprobe", cancel=None) -> dict:
    command = [executable, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path.resolve())]
    return run_json(command) if cancel is None else run_json(command, cancel)


def _duration(stream: dict, container: dict) -> Fraction:
    ticks, base = stream.get("duration_ts"), stream.get("time_base")
    if ticks is not None and str(ticks) != "N/A" and base and base != "0/0":
        value = Fraction(str(ticks)) * Fraction(str(base))
    else:
        raw = stream.get("duration")
        if raw in (None, "N/A"):
            raw = container.get("duration")
        if raw in (None, "N/A"):
            raise ValueError("Duração ausente nos metadados.")
        value = Fraction(str(raw))
    if value <= 0:
        raise ValueError("Duração inválida nos metadados.")
    return value


def source_timecode(value: str, fps: Fraction) -> Fraction:
    """Convert embedded SMPTE timecode to FCP's absolute source timeline."""
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})([:;])(\d{2})", value)
    if not match:
        raise ValueError(f"Timecode de fonte inválido: {value}")
    h, m, sec, frame = (int(match[i]) for i in (1, 2, 3, 5))
    nominal = round(fps)
    if h > 23 or m > 59 or sec > 59 or frame >= nominal:
        raise ValueError(f"Timecode de fonte inválido: {value}")
    frames = ((h * 60 + m) * 60 + sec) * nominal + frame
    if match[4] == ";":
        if fps not in (Fraction(30000, 1001), Fraction(60000, 1001)):
            raise ValueError(f"Drop-frame incompatível com FPS {fps}")
        drop = 2 if nominal == 30 else 4
        if m % 10 and sec == 0 and frame < drop:
            raise ValueError(f"Quadro inexistente em timecode drop-frame: {value}")
        minutes = h * 60 + m
        frames -= drop * (minutes - minutes // 10)
    return Fraction(frames) / fps


def video_from_probe(path: Path, data: dict, assume_timezone: str | None = None) -> Video:
    streams = data.get("streams", [])
    visual = next((s for s in streams if s.get("codec_type") == "video"
                   and not s.get("disposition", {}).get("attached_pic")), None)
    if visual is None:
        raise ValueError(f"Nenhuma faixa de vídeo em {path}.")
    container = data.get("format", {})
    sources = [("format", container.get("tags", {})), ("video", visual.get("tags", {}))]
    capture = None
    # Apple's capture timestamp can contain a local offset and subseconds that the
    # generic QuickTime creation_time (UTC, often whole seconds) does not contain.
    for tag in ("com.apple.quicktime.creationdate", "creation_time"):
        for scope, tags in sources:
            if tags.get(tag):
                capture = parse_timestamp(str(tags[tag]), f"{scope}.{tag}", assume_timezone)
                break
        if capture:
            break
    if capture is None:
        raise ValueError(f"Horário de captura ausente em {path}; datas do Windows não serão usadas.")
    fps = Fraction(0)
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = visual.get(key)
        if raw and raw != "0/0":
            fps = Fraction(str(raw))
            if fps > 0:
                break
    if fps <= 0:
        raise ValueError(f"Taxa de quadros ausente/inválida em {path}.")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    timecode = visual.get("tags", {}).get("timecode") or container.get("tags", {}).get("timecode")
    if not timecode:
        timecode = next((x.get("tags", {}).get("timecode") for x in streams
                         if x.get("codec_type") == "data" and x.get("tags", {}).get("timecode")), None)
    source_start = source_timecode(timecode, fps) if timecode else Fraction(str(visual.get("start_time", "0")))
    return Video(path.resolve(), capture, _duration(visual, container),
                 int(visual["width"]), int(visual["height"]), fps,
                 int(audio.get("channels", 0)), int(audio.get("sample_rate", 48000)),
                 source_start)


def photo_from_exif(path: Path, data: dict, assume_timezone: str | None = None) -> Photo:
    if data.get("ExifTool:Error") or data.get("Error"):
        raise ValueError(f"EXIF inválido em {path}: {data.get('ExifTool:Error', data.get('Error'))}")

    def tag(name):
        for group in ("ExifIFD", "EXIF", "IFD0", "File", "Composite"):
            if f"{group}:{name}" in data:
                return data[f"{group}:{name}"]
        return data.get(name)

    raw = tag("SubSecDateTimeOriginal")
    source = "EXIF.SubSecDateTimeOriginal"
    if not raw:
        raw = tag("DateTimeOriginal")
        if not raw:
            raise MissingPhotoCaptureTime(f"DateTimeOriginal ausente em {path}.")
        raw = str(raw)
        subsec, offset = tag("SubSecTimeOriginal"), tag("OffsetTimeOriginal")
        if subsec is not None and str(subsec).strip():
            digits = str(subsec).strip()
            if not digits.isdigit():
                raise ValueError(f"SubSecTimeOriginal inválido em {path}: {digits}")
            raw += "." + digits
        if offset:
            raw += str(offset)
        source = "EXIF.DateTimeOriginal+SubSecTimeOriginal+OffsetTimeOriginal"
    capture = parse_timestamp(str(raw), source, assume_timezone)
    width, height = tag("ImageWidth"), tag("ImageHeight")
    if not width or not height:
        raise ValueError(f"Dimensões JPEG ausentes em {path}.")
    return Photo(path.resolve(), capture, int(width), int(height))


class MetadataReader:
    def __init__(self, ffprobe: str = "ffprobe", exiftool: str = "exiftool",
                 assume_timezone: str | None = None, cancel=None):
        self.ffprobe, self.exiftool = ffprobe, exiftool
        self.assume_timezone = assume_timezone
        self.cancel = cancel
        self.skipped_missing_capture_time = []

    def video(self, path: Path) -> Video:
        return video_from_probe(path, probe(path, self.ffprobe, self.cancel), self.assume_timezone)

    def photos(self, paths: tuple[Path, ...]) -> list[Photo]:
        photos = []
        # One file per subprocess avoids Windows command-line limits and keeps
        # errors attributable. Batch/stay_open is a later performance improvement.
        for path in paths:
            check_cancel(self.cancel)
            command = [self.exiftool, "-j", "-G1", "-s", "-n",
                             "-DateTimeOriginal", "-SubSecTimeOriginal", "-OffsetTimeOriginal",
                             "-SubSecDateTimeOriginal", "-ImageWidth", "-ImageHeight",
                             str(path.resolve())]
            data = run_json(command) if self.cancel is None else run_json(command, self.cancel)
            if not isinstance(data, list) or len(data) != 1:
                raise ValueError(f"Resposta inesperada do ExifTool para {path}.")
            try:
                photos.append(photo_from_exif(path, data[0], self.assume_timezone))
            except MissingPhotoCaptureTime:
                self.skipped_missing_capture_time.append(path.resolve())
        return photos

    def sound(self, path: Path) -> Sound:
        data = probe(path, self.ffprobe, self.cancel)
        container = data.get("format", {})
        if "wav" not in container.get("format_name", "").split(","):
            raise ValueError(f"O arquivo não é um WAV: {path}")
        audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
        if audio is None:
            raise ValueError(f"Faixa de áudio ausente: {path}")
        return Sound(path.resolve(), _duration(audio, container), int(audio["channels"]),
                     int(audio["sample_rate"]))

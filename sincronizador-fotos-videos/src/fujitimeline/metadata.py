"""Read-only subprocess adapters. Never use filesystem dates as capture dates."""

import json
import os
import subprocess
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from .models import Photo, Sound, Video
from .temporal import parse_timestamp


def run_json(command: list[str]):
    try:
        completed = subprocess.run(command, check=True, capture_output=True,
                                   encoding="utf-8", errors="replace", timeout=120,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
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


def probe(path: Path, executable: str = "ffprobe") -> dict:
    return run_json([executable, "-v", "error", "-show_format", "-show_streams",
                     "-of", "json", str(path.resolve())])


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
    return Video(path.resolve(), capture, _duration(visual, container),
                 int(visual["width"]), int(visual["height"]), fps,
                 int(audio.get("channels", 0)), int(audio.get("sample_rate", 48000)),
                 Fraction(str(visual.get("start_time", "0"))))


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
            raise ValueError(f"DateTimeOriginal ausente em {path}.")
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
                 assume_timezone: str | None = None):
        self.ffprobe, self.exiftool = ffprobe, exiftool
        self.assume_timezone = assume_timezone

    def video(self, path: Path) -> Video:
        return video_from_probe(path, probe(path, self.ffprobe), self.assume_timezone)

    def photos(self, paths: tuple[Path, ...]) -> list[Photo]:
        photos = []
        # One file per subprocess avoids Windows command-line limits and keeps
        # errors attributable. Batch/stay_open is a later performance improvement.
        for path in paths:
            data = run_json([self.exiftool, "-j", "-G1", "-s", "-n",
                             "-DateTimeOriginal", "-SubSecTimeOriginal", "-OffsetTimeOriginal",
                             "-SubSecDateTimeOriginal", "-ImageWidth", "-ImageHeight",
                             str(path.resolve())])
            if not isinstance(data, list) or len(data) != 1:
                raise ValueError(f"Resposta inesperada do ExifTool para {path}.")
            photos.append(photo_from_exif(path, data[0], self.assume_timezone))
        return photos

    def sound(self, path: Path) -> Sound:
        data = probe(path, self.ffprobe)
        container = data.get("format", {})
        if "wav" not in container.get("format_name", "").split(","):
            raise ValueError(f"O arquivo não é um WAV: {path}")
        audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
        if audio is None:
            raise ValueError(f"Faixa de áudio ausente: {path}")
        return Sound(path.resolve(), _duration(audio, container), int(audio["channels"]),
                     int(audio["sample_rate"]))

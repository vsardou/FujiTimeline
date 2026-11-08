"""Exact temporal arithmetic. No machine-local timezone or clock calibration."""

import re
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import CaptureTime

_STAMP = re.compile(
    r"^(\d{4})[:-](\d{2})[:-](\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
    r"(?:[.,](\d+))?(Z|[+-]\d{2}:?\d{2})?$"
)


def parse_timestamp(raw: str, source: str, assume_timezone: str | None = None) -> CaptureTime:
    match = _STAMP.fullmatch(raw.strip())
    if not match:
        raise ValueError(f"Data inválida em {source}: {raw!r}")
    year, month, day, hour, minute, second, subsec, offset = match.groups()
    naive = datetime(*(int(x) for x in (year, month, day, hour, minute, second)))
    assumed = None
    if offset:
        zone_text = offset
    elif assume_timezone:
        zone_text = assume_timezone
        assumed = assume_timezone
    else:
        raise ValueError(f"{source}: horário sem fuso ({raw}). Informe --assume-timezone.")
    if zone_text in {"Z", "UTC"}:
        tz = timezone.utc
    elif re.fullmatch(r"[+-]\d{2}:?\d{2}", zone_text):
        normalized = zone_text.replace(":", "")
        hours, minutes = int(normalized[1:3]), int(normalized[3:5])
        if hours > 23 or minutes > 59:
            raise ValueError(f"Fuso inválido: {zone_text}")
        delta = timedelta(hours=hours, minutes=minutes)
        tz = timezone(-delta if normalized[0] == "-" else delta)
    else:
        try:
            tz = ZoneInfo(zone_text)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Fuso desconhecido: {zone_text}") from exc
        # Refuse DST ambiguity/nonexistent wall times instead of guessing a fold.
        early, late = naive.replace(tzinfo=tz, fold=0), naive.replace(tzinfo=tz, fold=1)
        if early.utcoffset() != late.utcoffset():
            raise ValueError(f"Horário ambíguo/inexistente em {zone_text}; informe offset UTC explícito.")
    aware = naive.replace(tzinfo=tz)
    delta = aware.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    epoch = Fraction(delta.days * 86400 + delta.seconds)
    if subsec:
        epoch += Fraction(int(subsec), 10 ** len(subsec))
    offset_seconds = int(aware.utcoffset().total_seconds())
    sign = "+" if offset_seconds >= 0 else "-"
    hours, seconds = divmod(abs(offset_seconds), 3600)
    normalized_offset = f"{sign}{hours:02}:{seconds // 60:02}"
    return CaptureTime(epoch, raw, source, normalized_offset, assumed)


def nearest_frame(seconds: Fraction, fps: Fraction) -> int:
    """Round half up, avoiding float and Python's ties-to-even behavior."""
    return (seconds * fps + Fraction(1, 2)).__floor__()


def floor_frame(seconds: Fraction, fps: Fraction) -> int:
    return (seconds * fps).__floor__()

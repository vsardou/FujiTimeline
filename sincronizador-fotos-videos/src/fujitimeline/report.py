"""Portable, auditable planning output; rational seconds are stored as strings."""

from dataclasses import asdict
from fractions import Fraction
import json
from pathlib import Path

from .models import Timeline


def to_json(timeline: Timeline) -> str:
    def encode(value):
        if isinstance(value, (Path, Fraction)):
            return str(value)
        raise TypeError(type(value).__name__)
    return json.dumps(asdict(timeline), default=encode, ensure_ascii=False, indent=2) + "\n"


def write_new(path: Path, content: str, suffix: str) -> None:
    """Exclusive create: even an output accidentally pointing at media cannot overwrite it."""
    if path.suffix.lower() != suffix:
        raise ValueError(f"O arquivo de saída deve terminar em {suffix}.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)

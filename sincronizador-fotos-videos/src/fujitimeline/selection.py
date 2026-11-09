from dataclasses import dataclass
from pathlib import Path
from .jobs import check_cancel


@dataclass(frozen=True)
class Inputs:
    videos: tuple[Path, ...]
    photos: tuple[Path, ...]
    sound: Path | None


def existing_file(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"Não é um arquivo: {resolved}")
    return resolved


def select_files(videos: list[Path], photo_dir: Path, sound: Path | None = None,
                 recursive: bool = False, cancel=None) -> Inputs:
    if not videos:
        raise ValueError("Selecione pelo menos um vídeo.")
    folder = photo_dir.expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError(f"Não é uma pasta: {folder}")
    selected_videos = tuple(dict.fromkeys(existing_file(p) for p in videos))
    files = folder.rglob("*") if recursive else folder.iterdir()
    found = set()
    for p in files:
        check_cancel(cancel)
        if p.suffix.lower() in {'.jpg', '.jpeg'} and p.is_file():
            found.add(p.resolve())
    photos = tuple(sorted(found, key=lambda p: str(p).casefold()))
    if not photos:
        raise ValueError(f"Nenhuma fotografia JPEG encontrada: {folder}")
    wav = existing_file(sound) if sound else None
    if wav and wav.suffix.lower() != ".wav":
        raise ValueError("O efeito de disparo deve ser um arquivo WAV.")
    return Inputs(selected_videos, photos, wav)

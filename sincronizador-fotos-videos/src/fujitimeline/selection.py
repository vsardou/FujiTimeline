from dataclasses import dataclass
from pathlib import Path


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
                 recursive: bool = False) -> Inputs:
    if not videos:
        raise ValueError("Selecione pelo menos um vídeo.")
    folder = photo_dir.expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError(f"Não é uma pasta: {folder}")
    selected_videos = tuple(dict.fromkeys(existing_file(p) for p in videos))
    files = folder.rglob("*") if recursive else folder.iterdir()
    photos = tuple(sorted({p.resolve() for p in files
                           if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}},
                          key=lambda p: str(p).casefold()))
    if not photos:
        raise ValueError(f"Nenhuma fotografia JPEG encontrada: {folder}")
    wav = existing_file(sound) if sound else None
    if wav and wav.suffix.lower() != ".wav":
        raise ValueError("O efeito de disparo deve ser um arquivo WAV.")
    return Inputs(selected_videos, photos, wav)

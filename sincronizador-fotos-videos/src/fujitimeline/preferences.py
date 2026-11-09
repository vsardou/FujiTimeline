"""Only folder preferences, stored locally outside the repository."""
import json
import os
from pathlib import Path
import sys


def location():
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return base / 'FujiTimeline' / 'folders.json'


def load(path=None):
    try:
        data = json.loads((path or location()).read_text(encoding='utf-8'))
        return {k: v for k, v in data.items() if k in {'last_dir', 'photos', 'output_dir'} and isinstance(v, str)}
    except (OSError, ValueError, AttributeError):
        return {}


def save(data, path=None):
    path = path or location()
    path.parent.mkdir(parents=True, exist_ok=True)
    filtered = {k: str(v) for k, v in data.items() if k in {'last_dir', 'photos', 'output_dir'}}
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(filtered, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)

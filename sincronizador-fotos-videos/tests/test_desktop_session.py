from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
from threading import Event, Timer
import json
import sys
import time

import pytest
from PIL import Image

from fujitimeline import desktop, preferences
from fujitimeline.desktop import Request, Session, manual_profile, thumbnail
from fujitimeline.demo import demo_timeline
from fujitimeline.jobs import Cancelled
from fujitimeline.metadata import run_json


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    demo = demo_timeline()
    video = tmp_path / 'movie.mov'
    video.write_bytes(b'video fixture')
    photos = {}
    for i, item in enumerate(demo.photos):
        path = tmp_path / f'photo-{i}.jpg'
        Image.new('RGB', (20, 10), 'green').save(path)
        photos[path] = replace(item.media, path=path)
    calls = []
    def read_video(self, path):
        calls.append(path)
        return replace(demo.videos[0].media, path=path)
    def read_photos(self, paths):
        calls.extend(paths)
        return [photos[p] for p in paths]
    monkeypatch.setattr(desktop.MetadataReader, 'video', read_video)
    monkeypatch.setattr(desktop.MetadataReader, 'photos', read_photos)
    request = Request((video,), tmp_path, manual_profile('0', ''), tmp_path / 'result.fcpxml')
    return request, calls, photos


def test_cache_recalculates_selection_without_rereading(inputs):
    request, calls, photos = inputs
    session = Session()
    first = session.run(request)
    assert len(calls) == 5
    request = replace(request, profile=manual_profile('-13', 'pair'))
    corrected = session.run(request)
    assert len(calls) == 5
    assert len(first.plan.photos) == 4 and len(corrected.plan.photos) == 3
    path = next(iter(photos))
    path.write_bytes(path.read_bytes() + b'changed')
    session.run(request)
    assert len(calls) == 6


def test_unchecking_rebuilds_durations_and_audits_original_times(inputs):
    request, calls, photos = inputs
    unchecked = list(photos)[1]
    request = replace(request, unchecked=frozenset({unchecked}))
    result = Session().run(request, export=True)
    assert len(result.plan.photos) == 3
    assert result.plan.photos[0].duration == F('7.17')
    assert result.plan.manually_excluded == [unchecked]
    report = json.loads(request.output.with_suffix('.json').read_text(encoding='utf-8'))
    assert len(report['photo_timings']) == 4
    assert report['photo_timings'][1]['selected'] is False
    assert report['manually_excluded'] == [str(unchecked)]


def test_cancel_during_metadata_does_not_create_output(inputs):
    request, calls, photos = inputs
    cancel = Event()
    def progress(done, total, text):
        if done == 1:
            cancel.set()
    with pytest.raises(Cancelled):
        Session().run(request, export=True, cancel=cancel, progress=progress)
    assert not request.output.exists()
    assert not request.output.with_suffix('.json').exists()
    assert len(calls) == 1


def test_subprocess_cancel_is_prompt():
    cancel = Event()
    timer = Timer(.2, cancel.set)
    timer.start()
    start = time.monotonic()
    try:
        with pytest.raises(Cancelled):
            run_json([sys.executable, '-c', 'import time; time.sleep(30)'], cancel)
        assert time.monotonic() - start < 5
    finally:
        timer.cancel()


def test_thumbnail_preserves_original(tmp_path):
    path = tmp_path / 'photo.jpg'
    Image.new('RGB', (600, 400), 'red').save(path)
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    result = thumbnail(path)
    assert result.width <= 72 and result.height <= 52
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_preferences_only_store_folders_and_tolerate_corruption(tmp_path):
    path = tmp_path / 'folders.json'
    preferences.save({'photos': 'photos', 'last_dir': 'last', 'offset': '-2.202', 'secret': 'discard'}, path)
    assert preferences.load(path) == {'photos': 'photos', 'last_dir': 'last'}
    path.write_text('broken')
    assert preferences.load(path) == {}

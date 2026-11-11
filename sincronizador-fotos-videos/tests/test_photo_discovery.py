from dataclasses import replace
from pathlib import Path
import json

import pytest

from fujitimeline import metadata
from fujitimeline.demo import demo_timeline
from fujitimeline.desktop import Request, Session, manual_profile


def test_mixed_folder_skips_undated_and_filters_corrected_video_period(tmp_path, monkeypatch):
    video = tmp_path / 'phone.mov'
    video.write_bytes(b'video')
    paths = [tmp_path / name for name in ('inside.jpg', 'outside.jpg', 'undated.jpg')]
    for path in paths:
        path.write_bytes(b'photo')
    original = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in [video, *paths]}
    calls = []
    def read_json(command):
        path = Path(command[-1])
        calls.append(path)
        data = {'File:ImageWidth': 100, 'File:ImageHeight': 50}
        if path.name != 'undated.jpg':
            data['Composite:SubSecDateTimeOriginal'] = (
                '2026:11:06 12:00:12.660-03:00' if path.name == 'inside.jpg'
                else '2026:11:07 12:00:12.660-03:00')
        return [data]
    monkeypatch.setattr(metadata, 'run_json', read_json)
    monkeypatch.setattr(metadata.MetadataReader, 'video', lambda self, path: replace(demo_timeline().videos[0].media, path=path))
    request = Request((video,), tmp_path, manual_profile('-2.272', 'pair'), tmp_path/'result.fcpxml')
    session = Session()
    first = session.run(request)
    assert [p.media.path.name for p in first.plan.photos] == ['inside.jpg']
    assert float(first.plan.photos[0].offset) == 10.388
    assert first.plan.excluded == [tmp_path/'outside.jpg']
    assert first.plan.skipped_missing_capture_time == [tmp_path/'undated.jpg']
    assert any('undated.jpg' in warning for warning in first.plan.warnings)
    second = session.run(request, export=True)
    assert len(calls) == 3  # Missing dates are cached too; warnings survive cache hits.
    report = json.loads(request.output.with_suffix('.json').read_text())
    assert report['skipped_missing_capture_time'] == [str(tmp_path/'undated.jpg')]
    assert second.plan.skipped_missing_capture_time == first.plan.skipped_missing_capture_time
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in original} == original


@pytest.mark.parametrize('data, message', [
    ({'Composite:SubSecDateTimeOriginal': 'invalid'}, 'inválid'),
    ({'Composite:SubSecDateTimeOriginal': '2026:11:06 12:00:12'}, 'sem fuso'),
    ({'ExifTool:Error': 'broken JPEG'}, 'EXIF inválido'),
])
def test_invalid_metadata_is_not_silently_skipped(monkeypatch, data, message):
    monkeypatch.setattr(metadata, 'run_json', lambda command: [data])
    with pytest.raises(ValueError, match=message):
        metadata.MetadataReader().photos((Path('photo.jpg'),))


def test_tool_failure_still_stops_discovery(monkeypatch):
    def failure(command):
        raise ValueError('Ferramenta não encontrada')
    monkeypatch.setattr(metadata, 'run_json', failure)
    with pytest.raises(ValueError, match='Ferramenta não encontrada'):
        metadata.MetadataReader().photos((Path('photo.jpg'),))

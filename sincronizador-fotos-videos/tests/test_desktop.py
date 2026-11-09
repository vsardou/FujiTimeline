from fractions import Fraction as F
from pathlib import Path

import pytest

from fujitimeline.desktop import Request, execute, manual_profile, seconds
from fujitimeline.demo import demo_timeline


@pytest.mark.parametrize('text,expected', [('0', '0'), ('-2,202', '-2.202'), ('+2.202', '2.202'),
    ('-00:02,202', '-2.202'), ('01:02:03,456', '3723.456'), ('1:30', '90')])
def test_seconds_precision(text, expected):
    assert seconds(text) == F(expected)


@pytest.mark.parametrize('text', ['', 'nan', 'inf', '1:60', '1:60:00', '1,2.3', '1/0'])
def test_seconds_rejects_invalid_input(text):
    with pytest.raises(ValueError):
        seconds(text)


def test_manual_correction_and_default():
    assert manual_profile('0', '').status == 'uncalibrated'
    with pytest.raises(ValueError, match='par'):
        manual_profile('-2,202', '')
    profile = manual_profile('-2,202', 'meu par')
    assert profile.status == 'experimental'
    plan = demo_timeline(profile=profile)
    assert plan.photos[0].offset == F('10.458')
    assert plan.photo_timings[0].original == demo_timeline().photo_timings[0].original


def test_existing_export_is_rejected_before_reading_media(tmp_path):
    target = tmp_path / 'timeline.fcpxml'
    report = target.with_suffix('.json')
    report.write_text('preservar', encoding='utf-8')
    request = Request((), tmp_path, manual_profile('0', ''), target)
    with pytest.raises(ValueError, match='sobrescritos'):
        execute(request, export=True)
    assert report.read_text() == 'preservar'
    assert not target.exists()


def test_desktop_workflow_exports_corrected_timeline(tmp_path, monkeypatch):
    from fujitimeline import desktop
    from fujitimeline.selection import Inputs
    baseline = demo_timeline()
    monkeypatch.setattr(desktop, 'select_files', lambda *a: Inputs((Path('v.mov'),), (Path('p.jpg'),), None))
    monkeypatch.setattr(desktop.MetadataReader, 'video', lambda *a: baseline.videos[0].media)
    monkeypatch.setattr(desktop.MetadataReader, 'photos', lambda *a: [p.media for p in baseline.photos])
    target = tmp_path / 'result.fcpxml'
    request = Request((Path('v.mov'),), tmp_path, manual_profile('-2,202', 'test'), target)
    preview = execute(request)
    assert not target.exists()
    exported = execute(request, export=True)
    assert preview.photos == exported.photos
    assert target.exists() and target.with_suffix('.json').exists()
    assert exported.photos[0].offset == F('10.458')

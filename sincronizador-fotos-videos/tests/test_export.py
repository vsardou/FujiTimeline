from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from fujitimeline.demo import demo_timeline
from fujitimeline.export_fcpxml import export_fcpxml, render_fcpxml, seconds
from fujitimeline.models import Sound
from fujitimeline.timeline import build_timeline


def test_standard_hd_format_matches_real_mac_import_checkpoint():
    xml, _ = render_fcpxml(demo_timeline(), F(30), width=1920, height=1080)
    root = ET.fromstring(xml)
    sequence = root.find('./project/sequence')
    fmt = next(f for f in root.findall('./resources/format') if f.get('id') == sequence.get('format'))
    assert fmt.get('name') == 'FFVideoFormat1080p30'
    assert fmt.get('frameDuration') == '1/30s'
    assert not root.find('./resources/format[@width="7728"]').get('name')


@pytest.mark.parametrize("fps", [F(30), F(25), F(30000, 1001)])
def test_export_resources_lanes_and_absolute_photo_times(fps):
    plan = demo_timeline(sound=Sound(Path("click.wav"), F("0.15")))
    xml, notes = render_fcpxml(plan, fps)
    root = ET.fromstring(xml)
    assert root.tag == "fcpxml" and root.get("version") == "1.8"
    assert not root.findall("./asset-clip")
    spine = root.find("./project/sequence/spine")
    assert len(spine) == 1
    assert spine[0].tag == "asset-clip"
    photos = spine.findall("./asset-clip/clip[@lane='1']")
    sounds = spine.findall("./asset-clip/asset-clip[@lane='-1']")
    assert len(photos) == len(sounds) == 4
    assert [seconds(x.get("offset")) for x in photos] == [seconds(x.get("offset")) for x in sounds]
    for expected, exported in zip(plan.photos, photos):
        assert abs(seconds(exported.get("offset")) - expected.offset) <= F(1, 2) / fps
        assert seconds(exported.get("duration")) > 0
    assets = root.findall("./resources/asset")
    assert len(assets) == 6
    for asset in assets:
        assert asset.get("src").startswith("file:///")
    assert any(a.get("src").endswith("click.wav") and a.get("hasAudio") == "1" for a in assets)
    assert any("cauda" in note for note in notes)
    assert plan.duration == F("24.398")  # Export does not mutate the exact plan.


def test_video_audio_and_quoted_unicode_paths_are_preserved(tmp_path):
    plan = demo_timeline()
    video = replace(plan.videos[0].media, path=tmp_path / "Vídeo d'água.mov", audio_channels=2)
    photo = replace(plan.photos[0].media, path=tmp_path / "foto d'água.jpg")
    xml, _ = render_fcpxml(build_timeline([video], [photo]))
    root = ET.fromstring(xml)
    asset = next(a for a in root.findall("./resources/asset") if a.get("src") == video.path.as_uri())
    assert asset.get("hasAudio") == "1"
    assert asset.get("audioChannels") == "2"
    assert any(a.get("src") == photo.path.as_uri() for a in root.findall("./resources/asset"))


def test_second_recording_uses_parent_relative_offset_and_source_start():
    demo = demo_timeline()
    first = replace(demo.videos[0].media, duration=F(10))
    second = replace(first, path=Path("second.mov"), source_start=F(2),
                     captured=replace(first.captured, utc=first.captured.utc + 100))
    photo = replace(demo.photos[0].media, captured=replace(first.captured, utc=first.captured.utc + 102))
    plan = build_timeline([second, first], [photo])
    root = ET.fromstring(render_fcpxml(plan)[0])
    spine = root.find("./project/sequence/spine")
    assert seconds(spine[1].get("offset")) == 10
    attached = spine[1].find("clip")
    assert seconds(attached.get("offset")) == 4  # local 2 + source start 2


@pytest.mark.parametrize("fps", [F(30), F(30000, 1001)])
def test_photo_exactly_at_second_recording_start_connects_to_second_clip(fps):
    demo = demo_timeline()
    first = demo.videos[0].media
    second = replace(first, path=Path("second.mov"), captured=replace(first.captured, utc=first.captured.utc + 100))
    photo = replace(demo.photos[0].media, captured=second.captured)
    root = ET.fromstring(render_fcpxml(build_timeline([first, second], [photo]), fps)[0])
    spine = root.find("./project/sequence/spine")
    assert spine[0].find("clip") is None
    assert seconds(spine[1].find("clip").get("offset")) == 0


def test_subframe_burst_is_not_silently_dropped():
    demo = demo_timeline()
    first = demo.photos[0].media
    second = replace(first, path=Path("burst.jpg"), captured=replace(first.captured, utc=first.captured.utc + F("0.001")))
    with pytest.raises(ValueError, match="mesmo quadro"):
        render_fcpxml(build_timeline([demo.videos[0].media], [first, second]))


def test_export_never_overwrites_existing_files(tmp_path):
    target = tmp_path / "existing.fcpxml"
    target.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_fcpxml(demo_timeline(), target)
    assert target.read_text(encoding="utf-8") == "keep"
    with pytest.raises(ValueError, match="fcpxml"):
        export_fcpxml(demo_timeline(), tmp_path / "original.mov")


def test_source_bytes_are_not_changed(tmp_path):
    demo = demo_timeline()
    video_path, photo_path = tmp_path / "original.mov", tmp_path / "original.jpg"
    video_path.write_bytes(b"fake video for read-only test")
    photo_path.write_bytes(b"fake photo for read-only test")
    video = replace(demo.videos[0].media, path=video_path)
    photo = replace(demo.photos[0].media, path=photo_path)
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in (video_path, photo_path)]
    export_fcpxml(build_timeline([video], [photo]), tmp_path / "result.fcpxml")
    after = [(p.read_bytes(), p.stat().st_mtime_ns) for p in (video_path, photo_path)]
    assert before == after


def test_portrait_source_rate_is_independent_of_project_rate():
    demo = demo_timeline()
    video = replace(demo.videos[0].media, width=1080, height=1920, fps=F(30000, 1001))
    plan = build_timeline([video], [demo.photos[0].media])
    root = ET.fromstring(render_fcpxml(plan, F(30))[0])
    formats = {f.get('id'): f for f in root.findall('./resources/format')}
    project_format = formats[root.find('./project/sequence').get('format')]
    asset = next(a for a in root.findall("./resources/asset") if a.get("src") == video.path.resolve().as_uri())
    source_format = formats[asset.get('format')]
    assert project_format.get('name') == 'FFVideoFormatCustom'
    assert project_format.get('frameDuration') == '1/30s'
    assert source_format.get('frameDuration') == '1001/30000s'
    assert source_format.get('id') != project_format.get('id')
    assert seconds(root.find('./project/sequence/spine/asset-clip/clip').get('offset')) == round(plan.photos[0].offset * 30) / F(30)


def test_audio_only_resource_does_not_claim_video_format():
    root = ET.fromstring(render_fcpxml(demo_timeline(sound=Sound(Path('click.wav'), F('0.15'))))[0])
    sound = next(a for a in root.findall('./resources/asset') if a.get('hasVideo') == '0')
    assert sound.get('format') is None

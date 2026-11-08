from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path

import pytest

from fujitimeline.demo import demo_timeline
from fujitimeline.models import Photo, Sound
from fujitimeline.timeline import build_timeline


def test_requested_24398_scenario_until_next():
    plan = demo_timeline()
    assert plan.duration == F("24.398")
    assert [p.offset for p in plan.photos] == list(map(F, ["12.660", "16.880", "19.830", "23.420"]))
    assert [p.duration for p in plan.photos] == list(map(F, ["4.220", "2.950", "3.590", "0.978"]))
    assert plan.photos[0].source_offset == F("12.660")  # No -2.272 calibration.
    assert not plan.excluded


def test_fixed_is_cut_at_next_photo_and_timeline_end():
    plan = demo_timeline(mode="fixed", fixed_duration=F(3))
    assert [p.duration for p in plan.photos] == list(map(F, ["3", "2.950", "3", "0.978"]))


def test_compaction_and_sorting_remove_only_recording_gaps():
    demo = demo_timeline()
    first = demo.videos[0].media
    second = replace(first, path=Path("second.mov"), captured=replace(first.captured, utc=first.captured.utc + 100))
    later_photo = replace(demo.photos[0].media, captured=replace(first.captured, utc=first.captured.utc + 102))
    plan = build_timeline([second, first], [later_photo])
    assert plan.videos[1].offset == F("24.398")
    assert plan.photos[0].offset == F("26.398")
    assert plan.duration == F("48.796")


def test_tolerance_edges_and_exclusion():
    video = demo_timeline().videos[0].media
    def photo(name, relative):
        return Photo(Path(name), replace(video.captured, utc=video.captured.utc + F(relative)))
    photos = [photo("before.jpg", "-1"), photo("after.jpg", "25.398"), photo("far.jpg", "90")]
    plan = build_timeline([video], photos, tolerance=F(1))
    assert [p.media.path.name for p in plan.photos] == ["before.jpg", "after.jpg"]
    assert all(p.clamped for p in plan.photos)
    assert plan.excluded == [Path("far.jpg")]
    assert plan.photos[0].offset == 0
    assert plan.photos[-1].offset < plan.duration
    assert not build_timeline([video], photos).photos


@pytest.mark.parametrize("tolerance", [F(-1), F("60.001")])
def test_tolerance_bounds(tolerance):
    with pytest.raises(ValueError, match="tolerância"):
        demo_timeline(tolerance=tolerance)


def test_shutter_is_repeated_and_trimmed():
    sound = Sound(Path("shutter.wav"), F(5))
    plan = demo_timeline(sound=sound)
    assert len(plan.sounds) == 4
    assert [s.offset for s in plan.sounds] == [p.offset for p in plan.photos]
    assert plan.sounds[-1].duration == F("0.978")
    assert plan.sounds[0].duration == F("4.220")


def test_duplicate_timestamps_are_explicit_error():
    plan = demo_timeline()
    photo = plan.photos[0].media
    with pytest.raises(ValueError, match="mesmo instante"):
        build_timeline([plan.videos[0].media], [photo, replace(photo, path=Path("duplicate.jpg"))])


def test_overlapping_recordings_do_not_duplicate_photos():
    plan = demo_timeline()
    first = plan.videos[0].media
    second = replace(first, path=Path("overlap.mov"), captured=replace(first.captured, utc=first.captured.utc + 1))
    result = build_timeline([first, second], [plan.photos[0].media])
    assert len(result.photos) == 1
    assert result.photos[0].video_index == 0
    assert any("sobrepostos" in w for w in result.warnings)

from fractions import Fraction as F
from pathlib import Path
from unittest.mock import patch
import subprocess

import pytest

from fujitimeline.metadata import MetadataReader, photo_from_exif, run_json, video_from_probe
from fujitimeline.temporal import parse_timestamp


def test_nanoseconds_and_offsets_are_preserved_exactly():
    local = parse_timestamp("2026:11:06 12:00:12.000000123-03:00", "EXIF")
    utc = parse_timestamp("2026-11-06T15:00:12Z", "video")
    assert local.utc - utc.utc == F(123, 10**9)
    assert local.offset == "-03:00"
    assert local.raw.endswith(".000000123-03:00")


def test_missing_timezone_requires_explicit_context():
    with pytest.raises(ValueError, match="sem fuso"):
        parse_timestamp("2026:11:06 12:00:00", "EXIF")
    stamp = parse_timestamp("2026:11:06 12:00:00", "EXIF", "America/Sao_Paulo")
    assert stamp.assumed_timezone == "America/Sao_Paulo"
    assert stamp.offset == "-03:00"


@pytest.mark.parametrize("raw", ["2026-11-01T01:30:00", "2026-03-08T02:30:00"])
def test_dst_ambiguity_and_nonexistent_time_are_rejected(raw):
    with pytest.raises(ValueError, match="ambíguo/inexistente"):
        parse_timestamp(raw, "EXIF", "America/New_York")


def test_exif_leading_zero_subseconds():
    photo = photo_from_exif(Path("sample.jpg"), {
        "ExifIFD:DateTimeOriginal": "2026:11:06 12:00:00", "ExifIFD:SubSecTimeOriginal": "0060",
        "ExifIFD:OffsetTimeOriginal": "-03:00", "File:ImageWidth": 100, "File:ImageHeight": 50,
    })
    assert photo.captured.utc - parse_timestamp("2026-11-06T15:00:00Z", "base").utc == F("0.006")


def test_ffprobe_prefers_apple_capture_and_exact_ticks():
    video = video_from_probe(Path("phone.mov"), {
        "format": {"tags": {"creation_time": "2026-11-06T15:00:00Z",
                             "com.apple.quicktime.creationdate": "2026-11-06T12:00:00.123-03:00"},
                   "duration": "25"},
        "streams": [{"codec_type": "video", "duration_ts": 24398, "time_base": "1/1000",
                     "avg_frame_rate": "30000/1001", "width": 1920, "height": 1080},
                    {"codec_type": "audio", "channels": 2, "sample_rate": "48000"}],
    })
    assert video.duration == F("24.398")
    assert video.fps == F(30000, 1001)
    assert video.captured.raw.endswith(".123-03:00")
    assert video.audio_channels == 2


def test_missing_capture_never_uses_filesystem_time():
    with pytest.raises(ValueError, match="captura ausente"):
        video_from_probe(Path("video.mov"), {"streams": [{"codec_type": "video"}]})


def test_missing_tool_and_bad_json_are_readable_errors():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(ValueError, match="Ferramenta não encontrada"):
            run_json(["ffprobe"])
    with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "broken", "")):
        with pytest.raises(ValueError, match="JSON inválida"):
            run_json(["exiftool"])


def test_exiftool_call_is_read_only_and_paths_are_separate_arguments(tmp_path):
    path = tmp_path / "a foto.jpg"
    response = [{"Composite:SubSecDateTimeOriginal": "2026:11:06 12:00:00.001-03:00",
                 "File:ImageWidth": 100, "File:ImageHeight": 50}]
    with patch("fujitimeline.metadata.run_json", return_value=response) as runner:
        assert len(MetadataReader().photos((path,))) == 1
    command = runner.call_args.args[0]
    assert command[-1] == str(path.resolve())
    assert not any("=" in argument for argument in command)


@pytest.mark.parametrize('tc,fps,expected', [
    ('08:30:32;19', F(30000, 1001), F(918061 * 1001, 30000)),
    ('01:00:00:00', F(25), F(3600)),
    ('00:01:00;02', F(30000, 1001), F(1800 * 1001, 30000)),
    ('00:10:00;00', F(30000, 1001), F(17982 * 1001, 30000)),
])
def test_embedded_source_timecode(tc, fps, expected):
    from fujitimeline.metadata import source_timecode
    assert source_timecode(tc, fps) == expected


def test_invalid_drop_frame_is_rejected():
    from fujitimeline.metadata import source_timecode
    with pytest.raises(ValueError):
        source_timecode('00:01:00;00', F(30000, 1001))


def test_video_probe_uses_embedded_timecode_separately_from_capture_time():
    data = {'format': {'duration': '17.951267', 'tags': {'creation_time': '2026-11-11T11:32:05Z'}},
            'streams': [{'codec_type': 'video', 'width': 1080, 'height': 1920,
                         'avg_frame_rate': '30000/1001', 'start_time': '0',
                         'tags': {'timecode': '08:30:32;19'}}]}
    result = video_from_probe(Path('test.mp4'), data)
    assert result.source_start == F(918061 * 1001, 30000)
    assert result.captured.raw == '2026-11-11T11:32:05Z'

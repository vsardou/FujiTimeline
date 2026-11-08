import json
from unittest.mock import patch

from fujitimeline.cli import main
from fujitimeline.selection import select_files


def test_demo_cli_needs_no_external_tools(tmp_path):
    xml, report = tmp_path / "demo.fcpxml", tmp_path / "demo.json"
    with patch("subprocess.run", side_effect=AssertionError("Must not probe simulated files")):
        assert main(["demo", "--output", str(xml), "--report", str(report)]) == 0
    assert xml.exists()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["duration"] == "12199/500"
    assert len(data["photos"]) == 4
    original = xml.read_bytes()
    assert main(["demo", "--output", str(xml)]) == 2
    assert xml.read_bytes() == original


def test_selection_mixed_case_deduplicates_and_recurses_only_when_requested(tmp_path):
    video = tmp_path / "movie.MOV"
    video.touch()
    (tmp_path / "photo.JPG").touch()
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "other.JpEg").touch()
    assert len(select_files([video, video], tmp_path).videos) == 1
    assert len(select_files([video], tmp_path).photos) == 1
    assert len(select_files([video], tmp_path, recursive=True).photos) == 2


def test_cli_rejects_tolerance_before_reading_media(tmp_path, capsys):
    assert main(["plan", "--video", "missing.mov", "--photos", str(tmp_path), "--tolerance", "61"]) == 2
    assert "tolerância" in capsys.readouterr().err


def test_export_cli_with_simulated_tool_responses_and_original_paths(tmp_path):
    video, photo, sound = tmp_path / "v.mov", tmp_path / "p.JPG", tmp_path / "s.wav"
    for p in (video, photo, sound):
        p.write_bytes(b"original bytes")
    video_data = {"format": {"tags": {"creation_time": "2026-11-06T15:00:00Z"}},
                  "streams": [{"codec_type": "video", "duration": "24.398", "width": 1080,
                               "height": 1920, "avg_frame_rate": "30/1"}]}
    sound_data = {"format": {"format_name": "wav"}, "streams": [
        {"codec_type": "audio", "duration": "0.2", "channels": 1, "sample_rate": "48000"}]}
    photo_data = [{"Composite:SubSecDateTimeOriginal": "2026:11:06 12:00:12.660-03:00",
                   "File:ImageWidth": 7728, "File:ImageHeight": 5152}]
    def tool_response(command):
        return {str(video): video_data, str(photo): photo_data, str(sound): sound_data}[command[-1]]
    with patch("fujitimeline.metadata.run_json", side_effect=tool_response):
        assert main(["export", "--video", str(video), "--photos", str(tmp_path),
                     "--shutter", str(sound), "--output", str(tmp_path / "real-paths.fcpxml"),
                     "--report", str(tmp_path / "report.json")]) == 0
    assert all(p.read_bytes() == b"original bytes" for p in (video, photo, sound))
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["photos"][0]["offset"] == "633/50"

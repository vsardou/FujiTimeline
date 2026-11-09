from dataclasses import replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction as F
import json
from pathlib import Path

import pytest

from fujitimeline.calibration import (
    EXPERIMENTAL_PRESET, CalibrationProfile, corrected_time, experimental_profile,
    load_profile, profile_digest, revise_profile, save_profile, select_profile,
    validate_offset, zero_profile,
)
from fujitimeline.cli import main
from fujitimeline.demo import demo_timeline
from fujitimeline.export_fcpxml import render_fcpxml, seconds
from fujitimeline.models import Photo
from fujitimeline.report import to_json
from fujitimeline.temporal import parse_timestamp
from fujitimeline.timeline import build_timeline


def evidence(offsets=None):
    """Synthetic test fixture; tests establish behavior, not an actual device calibration."""
    offsets = offsets or [F("-2.272")] * 4
    base = datetime(2026, 11, 6, 15, tzinfo=timezone.utc)
    matches = []
    for i, (position, offset) in enumerate(zip([10, 20, 80, 90], offsets)):
        original = base + timedelta(microseconds=int((position - offset) * 1_000_000))
        matches.append({"photo_id": f"photo-{i}.jpg", "video_id": "reference.mov",
                        "photo_time": original.isoformat(), "video_start": base.isoformat(),
                        "video_position_seconds": str(position)})
    return {"pair_id": "my-pair", "session_start": base.isoformat(),
            "session_end": (base + timedelta(seconds=100)).isoformat(), "matches": matches}


def test_zero_is_default_for_every_unselected_pair():
    plan = demo_timeline()
    assert plan.calibration.status == "uncalibrated"
    assert plan.calibration.offset_seconds == 0
    assert [p.offset for p in plan.photos] == list(map(F, ["12.660", "16.880", "19.830", "23.420"]))
    assert all(p.corrected_utc == p.original.utc for p in plan.photo_timings)
    assert select_profile(None, "another-pair").offset_seconds == 0


def test_experimental_negative_profile_advances_photos_preserving_exif():
    original = demo_timeline()
    corrected = demo_timeline(profile=experimental_profile("my-pair"))
    assert [p.offset for p in corrected.photos] == list(map(F, ["10.388", "14.608", "17.558", "21.148"]))
    assert [p.media for p in corrected.photos] == [p.media for p in original.photos]
    assert corrected.calibration.status == "experimental"
    data = json.loads(to_json(corrected))
    assert data["calibration"]["pair_id"] == "my-pair"
    assert data["photo_timings"][0]["original"]["raw"].endswith("12.660-03:00")
    assert data["photo_timings"][0]["corrected_time"] == "2026-11-06T12:00:10.388-03:00"
    assert data["photo_timings"][0]["offset_seconds"] == "-284/125"


def test_positive_offset_delays_photos():
    profile = CalibrationProfile("positive", "my-pair", F("0.5"), "experimental")
    plan = demo_timeline(profile=profile)
    assert plan.photos[0].offset == F("13.160")
    assert plan.photos[-1].offset == F("23.920")


@pytest.mark.parametrize("offset,expected", [("0", ["start.jpg", "end.jpg"]),
                                           ("0.3", ["before.jpg", "start.jpg"]),
                                           ("-0.3", ["end.jpg", "after.jpg"])])
def test_selection_uses_corrected_time_at_both_edges(offset, expected):
    video = replace(demo_timeline().videos[0].media, duration=F(10))
    photos = [Photo(Path(name), replace(video.captured, utc=video.captured.utc + F(position)))
              for name, position in [("before.jpg", "-0.2"), ("start.jpg", "0.1"),
                                     ("end.jpg", "9.9"), ("after.jpg", "10.2")]]
    profile = CalibrationProfile("edge", "my-pair", F(offset), "experimental")
    plan = build_timeline([video], photos, profile=profile)
    assert [p.media.path.name for p in plan.photos] == expected
    assert len(plan.photo_timings) == 4  # Excluded photos also remain auditable.
    assert sum(p.selected for p in plan.photo_timings) == 2


def test_tolerance_is_applied_after_correction_without_overwriting_capture():
    video = demo_timeline().videos[0].media
    original = replace(video.captured, utc=video.captured.utc + F("0.1"))
    photo = Photo(Path("edge.jpg"), original)
    profile = CalibrationProfile("edge", "my-pair", F("-0.3"), "experimental")
    assert not build_timeline([video], [photo], profile=profile).photos
    plan = build_timeline([video], [photo], profile=profile, tolerance=F("0.2"))
    assert plan.photos[0].clamped and plan.photos[0].offset == 0
    assert plan.photos[0].source_offset == F("-0.2")
    assert plan.photos[0].media.captured == original


def test_corrected_time_preserves_timezone_precision_and_date_rollover():
    stamp = parse_timestamp("2026-11-06T00:00:00.000000123-03:00", "EXIF")
    assert corrected_time(stamp, F("-2.272")) == "2026-11-05T23:59:57.728000123-03:00"
    assert corrected_time(stamp, F(1, 3)).endswith("s")


def test_profiles_save_reuse_and_refuse_pair_mismatch(tmp_path):
    path = tmp_path / "pair.profile.json"
    profile = experimental_profile("my-pair")
    save_profile(profile, path)
    assert load_profile(path) == profile
    assert select_profile(str(path), "my-pair") == profile
    with pytest.raises(ValueError, match="outro pair_id"):
        select_profile(str(path), "other")
    with pytest.raises(ValueError, match="pair-id"):
        select_profile(EXPERIMENTAL_PRESET, None)
    with pytest.raises(FileExistsError):
        save_profile(profile, path)


def test_validate_direction_and_value_with_early_and_late_matches():
    valid = validate_offset(F("-2.272"), "my-pair", evidence())
    assert valid.passed and valid.early_count == valid.late_count == 2
    assert valid.max_residual_seconds == 0 and valid.fitted_session_drift_seconds == 0
    wrong_sign = validate_offset(F("2.272"), "my-pair", evidence())
    assert not wrong_sign.passed and wrong_sign.max_residual_seconds == F("4.544")
    assert not validate_offset(F("-2"), "my-pair", evidence()).passed


@pytest.mark.parametrize("offset", [F(0), F("1.5"), F("-2.272")])
def test_recalibration_estimates_signed_offset_and_keeps_previous_revision(offset, tmp_path):
    previous = experimental_profile("my-pair")
    old_path = tmp_path / "v1.profile.json"
    save_profile(previous, old_path)
    original_bytes = old_path.read_bytes()
    updated = revise_profile(previous, evidence([offset] * 4), recalibrate=True)
    assert updated.offset_seconds == offset and updated.status == "validated"
    assert updated.revision == 2 and updated.previous_digest == profile_digest(previous)
    new_path = tmp_path / "v2.profile.json"
    save_profile(updated, new_path)
    assert load_profile(new_path) == updated
    assert old_path.read_bytes() == original_bytes


def test_drift_prevents_constant_offset_being_marked_validated():
    measurements = evidence(list(map(F, ["-2.272", "-2.272", "-2.352", "-2.352"])))
    updated = revise_profile(experimental_profile("my-pair"), measurements, recalibrate=True)
    assert updated.status == "experimental"
    assert abs(updated.validation.end_to_start_drift_seconds) == F("0.08")
    assert any("deriva" in reason for reason in updated.validation.reasons)


def test_insufficient_or_one_end_only_evidence_cannot_validate():
    data = evidence()
    data["matches"] = data["matches"][:2]
    assert not validate_offset(F("-2.272"), "my-pair", data).passed
    data = evidence()
    data["session_end"] = "2026-11-06T15:10:00+00:00"
    assert not validate_offset(F("-2.272"), "my-pair", data).passed


def test_duplicate_photos_and_wrong_pair_are_rejected():
    data = evidence()
    data["matches"][1] = dict(data["matches"][0])
    with pytest.raises(ValueError, match="distintas"):
        validate_offset(F("-2.272"), "my-pair", data)
    with pytest.raises(ValueError, match="pair_id"):
        validate_offset(F("-2.272"), "wrong", evidence())


def test_synthetic_evidence_and_tampered_validated_profile_do_not_pass(tmp_path):
    data = evidence()
    data["synthetic"] = True
    assert not revise_profile(experimental_profile("my-pair"), data).validation.passed
    path = tmp_path / "valid.profile.json"
    save_profile(revise_profile(experimental_profile("my-pair"), evidence()), path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["offset_seconds"] = "2.272"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="não comprova"):
        load_profile(path)
    with pytest.raises(ValueError, match="evidências"):
        demo_timeline(profile=CalibrationProfile("forged", "my-pair", F(-1), "validated"))


def test_cli_create_reuse_and_recalibrate_without_tools(tmp_path):
    profile = tmp_path / "v1.profile.json"
    assert main(["profile", "create", "--pair-id", "my-pair", "--preset", EXPERIMENTAL_PRESET,
                 "--output", str(profile)]) == 0
    report = tmp_path / "report.json"
    assert main(["demo", "--profile", str(profile), "--pair-id", "my-pair", "--report", str(report)]) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["photos"][0]["offset"] == "2597/250"
    matches = tmp_path / "session.evidence.json"
    matches.write_text(json.dumps(evidence([F("1.5")] * 4)), encoding="utf-8")
    updated = tmp_path / "v2.profile.json"
    assert main(["profile", "recalibrate", "--profile", str(profile), "--evidence", str(matches),
                 "--output", str(updated)]) == 0
    assert load_profile(updated).offset_seconds == F("1.5")
    assert load_profile(profile).offset_seconds == F("-2.272")


def test_cli_failed_validation_saves_experimental_revision_and_returns_error(tmp_path):
    profile, matches = tmp_path / "v1.profile.json", tmp_path / "evidence.json"
    save_profile(experimental_profile("my-pair"), profile)
    matches.write_text(json.dumps(evidence([F("2.272")] * 4)), encoding="utf-8")
    updated = tmp_path / "v2.profile.json"
    assert main(["profile", "validate", "--profile", str(profile), "--evidence", str(matches),
                 "--output", str(updated)]) == 2
    assert load_profile(updated).status == "experimental"


def test_fcpxml_uses_corrected_positions_and_shutter_together():
    from xml.etree import ElementTree as ET
    from fujitimeline.models import Sound
    plan = demo_timeline(profile=experimental_profile("my-pair"), sound=Sound(Path("click.wav"), F("0.1")))
    root = ET.fromstring(render_fcpxml(plan)[0])
    parent = root.find("./project/sequence/spine/asset-clip")
    photos = parent.findall("clip[@lane='1']")
    sounds = parent.findall("asset-clip[@lane='-1']")
    assert len(photos) == len(sounds) == 4
    assert seconds(photos[0].get("offset")) == F("10.4")
    assert [p.get("offset") for p in photos] == [s.get("offset") for s in sounds]

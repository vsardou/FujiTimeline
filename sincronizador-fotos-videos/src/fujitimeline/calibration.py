"""Explicit, versioned pair profiles; original media timestamps never change."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from .models import CaptureTime
from .report import write_new
from .temporal import parse_timestamp

EXPERIMENTAL_PRESET = "experimental-minus-2.272"
SIGN = "corrected_photo_time = original_photo_time + offset_seconds"


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    reasons: tuple[str, ...]
    match_count: int
    early_count: int
    late_count: int
    suggested_offset_seconds: Fraction | None
    max_residual_seconds: Fraction | None
    end_to_start_drift_seconds: Fraction | None
    fitted_session_drift_seconds: Fraction | None
    residual_tolerance_seconds: Fraction
    drift_tolerance_seconds: Fraction


@dataclass(frozen=True)
class CalibrationProfile:
    name: str
    pair_id: str | None
    offset_seconds: Fraction = Fraction(0)
    status: str = "uncalibrated"
    revision: int = 1
    previous_digest: str | None = None
    evidence: dict | None = None
    validation: ValidationResult | None = None


def zero_profile(pair_id: str | None = None) -> CalibrationProfile:
    return CalibrationProfile("zero", pair_id)


def experimental_profile(pair_id: str) -> CalibrationProfile:
    if not pair_id or not pair_id.strip():
        raise ValueError("Informe --pair-id com um identificador local do par Fujifilm/iPhone.")
    return CalibrationProfile(EXPERIMENTAL_PRESET, pair_id, Fraction("-2.272"), "experimental")


def corrected_time(original: CaptureTime, offset: Fraction) -> str:
    """Readable exact local time; rational suffix for nonterminating fractions."""
    zone = original.offset.replace(":", "")
    zone_seconds = (int(zone[1:3]) * 3600 + int(zone[3:5]) * 60) * (-1 if zone[0] == "-" else 1)
    local = original.utc + offset + zone_seconds
    whole = local.__floor__()
    fraction = local - whole
    base = (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=whole)).strftime("%Y-%m-%dT%H:%M:%S")
    denominator, twos, fives = fraction.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return f"{base}{original.offset} + {fraction}s"
    digits = max(twos, fives)
    suffix = f".{int(fraction * 10**digits):0{digits}d}" if digits else ""
    return base + suffix + original.offset


def _median(values: list[Fraction]) -> Fraction:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream, parse_float=Decimal)
    if not isinstance(data, dict):
        raise ValueError("O JSON de perfil/evidências deve ser um objeto.")
    return data


def _evidence_points(evidence: dict, pair_id: str):
    if not isinstance(evidence, dict):
        raise ValueError("As evidências devem ser um objeto JSON.")
    if evidence.get("pair_id") != pair_id:
        raise ValueError("O pair_id das evidências não corresponde ao perfil.")
    if "synthetic" in evidence and not isinstance(evidence["synthetic"], bool):
        raise ValueError("synthetic deve ser true ou false.")
    start = parse_timestamp(evidence["session_start"], "evidence.session_start").utc
    end = parse_timestamp(evidence["session_end"], "evidence.session_end").utc
    if end <= start:
        raise ValueError("As evidências precisam delimitar uma sessão com início e fim distintos.")
    matches = evidence.get("matches")
    if not isinstance(matches, list):
        raise ValueError("As evidências devem conter uma lista matches.")
    points = []
    photo_ids, instants = set(), set()
    for match in matches:
        if not isinstance(match, dict):
            raise ValueError("Cada correspondência deve ser um objeto.")
        photo_id, video_id = match.get("photo_id"), match.get("video_id")
        if not isinstance(photo_id, str) or not photo_id.strip() or not isinstance(video_id, str) or not video_id.strip():
            raise ValueError("Cada correspondência precisa de photo_id e video_id identificáveis.")
        photo = parse_timestamp(match["photo_time"], "evidence.photo_time").utc
        video_start = parse_timestamp(match["video_start"], "evidence.video_start").utc
        position = Fraction(str(match["video_position_seconds"]))
        if position < 0:
            raise ValueError("A posição da correspondência no vídeo não pode ser negativa.")
        reference = video_start + position
        if not start <= reference <= end:
            raise ValueError("Correspondência fora dos limites da sessão informada.")
        if photo_id in photo_ids or photo in instants:
            raise ValueError("Correspondências devem usar fotografias distintas, sem repetir o mesmo instante.")
        photo_ids.add(photo_id)
        instants.add(photo)
        points.append((reference - start, reference - photo))
    return end - start, sorted(points)


def validate_offset(offset: Fraction, pair_id: str, evidence: dict,
                    residual_tolerance: Fraction = Fraction("0.1"),
                    drift_tolerance: Fraction = Fraction("0.05")) -> ValidationResult:
    if not 0 < residual_tolerance <= 1 or not 0 < drift_tolerance <= 1:
        raise ValueError("Tolerâncias de validação devem ser positivas e no máximo 1 segundo.")
    span, points = _evidence_points(evidence, pair_id)
    early = [y for x, y in points if x <= span / 5]
    late = [y for x, y in points if x >= span * 4 / 5]
    offsets = [y for _, y in points]
    reasons = []
    if evidence.get("synthetic", False):
        reasons.append("Dados declarados simulados não validam um perfil de aparelhos reais.")
    if len(points) < 4 or len(early) < 2 or len(late) < 2:
        reasons.append("Exige ao menos quatro fotos distintas: duas nos primeiros 20% e duas nos últimos 20% da sessão.")
    suggested = _median(offsets) if offsets else None
    max_residual = max((abs(y - offset) for y in offsets), default=None)
    if max_residual is not None and max_residual > residual_tolerance:
        reasons.append("Sinal/valor do offset não corresponde às evidências dentro da tolerância residual.")
    edge_drift = _median(late) - _median(early) if early and late else None
    fitted_drift = None
    if len(points) >= 2:
        mean_x = sum(x for x, _ in points) / len(points)
        mean_y = sum(offsets) / len(points)
        variance = sum((x - mean_x) ** 2 for x, _ in points)
        if variance:
            fitted_drift = sum((x - mean_x) * (y - mean_y) for x, y in points) / variance * span
    if any(value is not None and abs(value) > drift_tolerance for value in (edge_drift, fitted_drift)):
        reasons.append("Possível deriva entre relógios: um offset constante não valida esta sessão.")
    return ValidationResult(not reasons, tuple(reasons), len(points), len(early), len(late), suggested,
                            max_residual, edge_drift, fitted_drift, residual_tolerance, drift_tolerance)


def _json_text(payload: dict, *, compact=False) -> str:
    def encode(value):
        if isinstance(value, (Fraction, Decimal)):
            return str(value)
        raise TypeError(type(value).__name__)
    return json.dumps(payload, default=encode, ensure_ascii=False, sort_keys=True,
                      indent=None if compact else 2) + "\n"


def profile_payload(profile: CalibrationProfile) -> dict:
    return {"schema_version": 1, "sign_convention": SIGN, **asdict(profile)}


def profile_digest(profile: CalibrationProfile) -> str:
    return hashlib.sha256(_json_text(profile_payload(profile), compact=True).encode("utf-8")).hexdigest()


def profile_json(profile: CalibrationProfile) -> str:
    return _json_text(profile_payload(profile))


def check_profile(profile: CalibrationProfile) -> None:
    if not isinstance(profile.name, str) or not profile.name.strip():
        raise ValueError("Perfil precisa de um nome.")
    if isinstance(profile.revision, bool) or not isinstance(profile.revision, int) or profile.revision < 1:
        raise ValueError("Revisão de perfil inválida.")
    if profile.status not in {"uncalibrated", "experimental", "validated"}:
        raise ValueError("Status de perfil inválido.")
    if profile.status == "uncalibrated" and profile.offset_seconds != 0:
        raise ValueError("Um par não calibrado deve usar offset zero.")
    if profile.status != "uncalibrated" and (not isinstance(profile.pair_id, str) or not profile.pair_id.strip()):
        raise ValueError("Perfil precisa identificar o par Fujifilm/iPhone, sem inferir modelos.")
    if profile.status == "validated":
        if profile.evidence is None or profile.validation is None:
            raise ValueError("Perfil validado precisa conter evidências e resultado verificável.")
        actual = validate_offset(profile.offset_seconds, profile.pair_id, profile.evidence,
                                 profile.validation.residual_tolerance_seconds,
                                 profile.validation.drift_tolerance_seconds)
        if not actual.passed or actual != profile.validation:
            raise ValueError("Perfil diz validated, mas a evidência não comprova esse status.")


def save_profile(profile: CalibrationProfile, path: Path) -> None:
    check_profile(profile)
    if not path.name.endswith(".profile.json"):
        raise ValueError("Salve perfis com extensão .profile.json; são dados locais ignorados pelo Git.")
    write_new(path, profile_json(profile), ".json")


def load_profile(path: Path) -> CalibrationProfile:
    data = read_json(path)
    if data.get("schema_version") != 1 or data.get("sign_convention") != SIGN:
        raise ValueError("Versão ou convenção de sinal do perfil não reconhecida.")
    validation = None
    if data.get("validation") is not None:
        result = data["validation"]
        validation = ValidationResult(
            result["passed"], tuple(result["reasons"]), result["match_count"], result["early_count"], result["late_count"],
            *(Fraction(str(result[k])) if result[k] is not None else None for k in (
                "suggested_offset_seconds", "max_residual_seconds", "end_to_start_drift_seconds", "fitted_session_drift_seconds")),
            Fraction(str(result["residual_tolerance_seconds"])), Fraction(str(result["drift_tolerance_seconds"])),
        )
    profile = CalibrationProfile(data["name"], data["pair_id"], Fraction(str(data["offset_seconds"])),
                                 data["status"], data["revision"], data.get("previous_digest"),
                                 data.get("evidence"), validation)
    check_profile(profile)
    return profile


def select_profile(selection: str | None, pair_id: str | None) -> CalibrationProfile:
    if selection is None:
        return zero_profile(pair_id)
    if not pair_id or not pair_id.strip():
        raise ValueError("Use --pair-id para selecionar explicitamente o par do perfil.")
    profile = experimental_profile(pair_id) if selection == EXPERIMENTAL_PRESET else load_profile(Path(selection))
    if profile.pair_id != pair_id:
        raise ValueError("O perfil pertence a outro pair_id; o offset não foi aplicado.")
    return profile


def revise_profile(profile: CalibrationProfile, evidence: dict, *, recalibrate: bool = False,
                   residual_tolerance: Fraction = Fraction("0.1"),
                   drift_tolerance: Fraction = Fraction("0.05")) -> CalibrationProfile:
    check_profile(profile)
    if not profile.pair_id:
        raise ValueError("Informe um perfil associado a um par antes de validar/recalibrar.")
    offset = profile.offset_seconds
    if recalibrate:
        _, points = _evidence_points(evidence, profile.pair_id)
        if not points:
            raise ValueError("Recalibração precisa de correspondências foto/vídeo.")
        offset = _median([y for _, y in points])
    result = validate_offset(offset, profile.pair_id, evidence, residual_tolerance, drift_tolerance)
    return replace(profile, offset_seconds=offset, status="validated" if result.passed else "experimental",
                   revision=profile.revision + 1, previous_digest=profile_digest(profile),
                   evidence=evidence, validation=result)

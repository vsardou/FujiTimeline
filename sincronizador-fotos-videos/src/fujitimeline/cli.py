import argparse
from fractions import Fraction
from pathlib import Path
import sys

from .calibration import (EXPERIMENTAL_PRESET, CalibrationProfile, experimental_profile,
                          load_profile, profile_json, read_json, revise_profile,
                          save_profile, select_profile)
from .demo import demo_timeline
from .export_fcpxml import export_fcpxml
from .metadata import MetadataReader
from .report import to_json, write_new
from .selection import select_files
from .timeline import build_timeline


def fraction(value: str) -> Fraction:
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise argparse.ArgumentTypeError("Use segundos com ponto decimal ou uma fração, por exemplo 24.398.") from exc


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="FujiTimeline: sincronização por metadados, sem renderização.")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("plan", "export", "demo"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--mode", choices=["until_next", "fixed"], default="until_next")
        cmd.add_argument("--fixed-duration", type=fraction, default=Fraction(3))
        cmd.add_argument("--fps", type=fraction, default=Fraction(30))
        cmd.add_argument("--name", default="FujiTimeline")
        cmd.add_argument("--output", type=Path, help="JSON para plan; FCPXML para export/demo. Nunca sobrescreve.")
        cmd.add_argument("--report", type=Path, help="Relatório JSON com tempos exatos e avisos.")
        cmd.add_argument("--width", type=int)
        cmd.add_argument("--height", type=int)
        cmd.add_argument("--profile", help=f"Arquivo .profile.json ou preset {EXPERIMENTAL_PRESET}; omitido = zero.")
        cmd.add_argument("--pair-id", help="Identificador local do par Fujifilm/iPhone; obrigatório ao selecionar perfil.")
        if name != "demo":
            cmd.add_argument("--video", type=Path, nargs="+", required=True)
            cmd.add_argument("--photos", type=Path, required=True)
            cmd.add_argument("--recursive", action="store_true")
            cmd.add_argument("--shutter", type=Path)
            cmd.add_argument("--tolerance", type=fraction, default=Fraction(0))
            cmd.add_argument("--assume-timezone", help="Somente para metadados sem fuso: America/Sao_Paulo ou -03:00.")
            cmd.add_argument("--ffprobe", default="ffprobe")
            cmd.add_argument("--exiftool", default="exiftool")
    profiles = commands.add_parser("profile", help="Criar, inspecionar, validar e recalibrar perfis locais.")
    operations = profiles.add_subparsers(dest="profile_command", required=True)
    create = operations.add_parser("create")
    create.add_argument("--pair-id", required=True)
    create.add_argument("--name")
    offset = create.add_mutually_exclusive_group(required=True)
    offset.add_argument("--offset", type=fraction)
    offset.add_argument("--preset", choices=[EXPERIMENTAL_PRESET])
    create.add_argument("--output", type=Path, required=True)
    inspect = operations.add_parser("inspect")
    inspect.add_argument("--profile", type=Path, required=True)
    for action in ("validate", "recalibrate"):
        cmd = operations.add_parser(action)
        cmd.add_argument("--profile", type=Path, required=True)
        cmd.add_argument("--evidence", type=Path, required=True)
        cmd.add_argument("--output", type=Path, required=True, help="Nova revisão; nunca sobrescreve a anterior.")
        cmd.add_argument("--residual-tolerance", type=fraction, default=Fraction("0.1"))
        cmd.add_argument("--drift-tolerance", type=fraction, default=Fraction("0.05"))
    return result


def profile_command(args) -> int:
    if args.profile_command == "create":
        if args.preset:
            profile = experimental_profile(args.pair_id)
            if args.name:
                from dataclasses import replace
                profile = replace(profile, name=args.name)
        else:
            profile = CalibrationProfile(args.name or args.pair_id, args.pair_id, args.offset, "experimental")
    else:
        profile = load_profile(args.profile)
        if args.profile_command == "inspect":
            print(profile_json(profile), end="")
            return 0
        profile = revise_profile(profile, read_json(args.evidence),
                                 recalibrate=args.profile_command == "recalibrate",
                                 residual_tolerance=args.residual_tolerance,
                                 drift_tolerance=args.drift_tolerance)
    save_profile(profile, args.output)
    print(f"Perfil salvo: {args.output.resolve()} | revisão {profile.revision} | offset {profile.offset_seconds}s | {profile.status}")
    if profile.validation and not profile.validation.passed:
        for reason in profile.validation.reasons:
            print(f"Não validado: {reason}", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    try:
        if args.command == "profile":
            return profile_command(args)
        options = dict(mode=args.mode, fixed_duration=args.fixed_duration, fps=args.fps, name=args.name,
                       profile=select_profile(args.profile, args.pair_id))
        if args.command == "demo":
            plan = demo_timeline(**options)
            plan.warnings.append("DEMONSTRAÇÃO: metadados simulados; os caminhos example-media não contêm mídias reais.")
        else:
            if not 0 <= args.tolerance <= 60:
                raise ValueError("A tolerância deve estar entre 0 e 60 segundos.")
            inputs = select_files(args.video, args.photos, args.shutter, args.recursive)
            reader = MetadataReader(args.ffprobe, args.exiftool, args.assume_timezone)
            plan = build_timeline([reader.video(p) for p in inputs.videos], reader.photos(inputs.photos),
                                  sound=reader.sound(inputs.sound) if inputs.sound else None,
                                  tolerance=args.tolerance, **options)
        output = args.output
        if args.command == "export" and output is None:
            output = Path("output/FujiTimeline.fcpxml")
        outputs = [(output, ".json" if args.command == "plan" else ".fcpxml"), (args.report, ".json")]
        resolved = [p.resolve() for p, _ in outputs if p]
        if len(resolved) != len(set(resolved)):
            raise ValueError("Saída e relatório precisam ser arquivos distintos.")
        for path, suffix in outputs:
            if path and (path.exists() or path.suffix.lower() != suffix):
                raise ValueError(f"Saída deve ser um arquivo novo com extensão {suffix}: {path}")
        if output:
            if args.command == "plan":
                write_new(output, to_json(plan), ".json")
            else:
                plan.warnings.extend(export_fcpxml(plan, output, fps=args.fps, width=args.width, height=args.height))
            print(f"Criado: {output.resolve()}")
        if args.report:
            write_new(args.report, to_json(plan), ".json")
            print(f"Relatório: {args.report.resolve()}")
        if not output and not args.report:
            print(to_json(plan), end="")
        print(f"Vídeos: {len(plan.videos)} | Fotos: {len(plan.photos)} | Excluídas: {len(plan.excluded)}", file=sys.stderr)
        for warning in plan.warnings:
            print(f"Aviso: {warning}", file=sys.stderr)
        return 0
    except (ValueError, OSError, KeyError, TypeError, ZeroDivisionError, OverflowError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

import argparse
from fractions import Fraction
from pathlib import Path
import sys

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
        if name != "demo":
            cmd.add_argument("--video", type=Path, nargs="+", required=True)
            cmd.add_argument("--photos", type=Path, required=True)
            cmd.add_argument("--recursive", action="store_true")
            cmd.add_argument("--shutter", type=Path)
            cmd.add_argument("--tolerance", type=fraction, default=Fraction(0))
            cmd.add_argument("--assume-timezone", help="Somente para metadados sem fuso: America/Sao_Paulo ou -03:00.")
            cmd.add_argument("--ffprobe", default="ffprobe")
            cmd.add_argument("--exiftool", default="exiftool")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    try:
        options = dict(mode=args.mode, fixed_duration=args.fixed_duration, fps=args.fps, name=args.name)
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
    except (ValueError, OSError, KeyError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

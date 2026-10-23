"""Command line: `python -m xp_plus <command>`.

    gate    EXTRACTION.json                     report the completeness gate only
    run     EXTRACTION.json [--resolutions R.json] [--observations O.json] [--out S.json]
    schema  [--out xp-plus-standard.schema.json]  JSON schema of the Standard
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import TypeAdapter

from .extraction import FixtureExtractor
from .physical import RecordedRunner
from .pipeline import run_pipeline
from .schema import ReproStandard, Resolution
from .twin import TwinOptions, run_gate


def _print_gaps(gaps) -> None:
    for g in gaps:
        flag = "BLOCKING" if g.blocking else "        "
        print(f"  [{g.status:8}] {flag} {g.detected_by:16} {g.target}\n{'':39}{g.description}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="xp-plus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate")
    g.add_argument("extraction")
    r = sub.add_parser("run")
    r.add_argument("extraction")
    r.add_argument("--resolutions")
    r.add_argument("--observations", help="PhysicalRecord JSON (recorded run)")
    r.add_argument("--out", default="standard.json")
    r.add_argument("--twin-bodenstein", type=float, help="give reactors ADM dispersion with this Bo")
    r.add_argument("--no-connection-holdup", action="store_true",
                   help="ignore reported connection tubing volume (e.g. reactor-only timing)")
    r.add_argument("--black-box", metavar="MODEL_ID", help="twin output from this model card (fidelity black_box)")
    r.add_argument("--model-backend", default="botorch", help="botorch | botorch_legacy | sklearn")
    s = sub.add_parser("schema")
    s.add_argument("--out")
    p = sub.add_parser("api", help="serve only the XP Plus API (/xpp/api on :8765)")
    p.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)

    if args.cmd == "api":
        from .app import serve
        serve(port=args.port)
        return 0

    if args.cmd == "schema":
        text = ReproStandard.json_schema()
        Path(args.out).write_text(text, encoding="utf-8") if args.out else print(text)
        return 0

    extraction = FixtureExtractor().extract(args.extraction)
    if args.cmd == "gate":
        report = run_gate(extraction.features)
        print(f"gate {'PASSED' if report.passed else 'BLOCKED'}: {len(report.gaps)} gaps")
        _print_gaps(report.gaps)
        return 0 if report.passed else 1

    resolutions = []
    if args.resolutions:
        resolutions = TypeAdapter(list[Resolution]).validate_json(Path(args.resolutions).read_bytes())
    physical = RecordedRunner(args.observations) if args.observations else None
    options = TwinOptions(bodenstein=args.twin_bodenstein, connection_holdup=not args.no_connection_holdup,
                          black_box=args.black_box, black_box_backend=args.model_backend)
    std = run_pipeline(extraction, resolutions=resolutions, physical=physical, twin_options=options,
                       model_backend=args.model_backend)
    std.save(args.out)

    print(f"{std.standard_id}: verdict {std.verdict.upper()}  ->  {args.out}")
    print(f"gaps ({len(std.gaps)}):")
    _print_gaps(std.gaps)
    if std.twin:
        print("twin predictions:", json.dumps({k: f"{v.value:.4g} {v.unit}" for k, v in std.twin.predictions.items()}))
    fmt = lambda v: "-" if v is None else f"{v:.4g}"
    for row in std.results:
        comp = (f" | computational {fmt(row.computational)} ({row.computational_verdict})"
                if row.computational is not None else "")
        print(f"  {row.claim_id} {row.metric} [{row.unit or ''}]: paper {row.paper} | twin {fmt(row.twin)} "
              f"({row.twin_verdict}) | physical {fmt(row.physical)} ({row.physical_verdict}){comp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

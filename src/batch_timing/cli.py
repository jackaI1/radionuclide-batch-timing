"""Command-line interface; no network or server is used during simulation."""

import argparse
import json
import sys
from pathlib import Path

from .decay import snapshot
from .report import build_document, html_report, markdown_report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Educational radionuclide batch timing simulator")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "data", help="Print pinned NuDat ground-state fields and provenance as JSON"
    )
    run = commands.add_parser("run", help="Run a JSON scenario and export a portable study")
    run.add_argument("scenario", type=Path)
    run.add_argument("--samples", type=int, default=20000)
    run.add_argument("--seed", type=int, default=2026)
    for option in ("json", "html", "markdown"):
        run.add_argument("--" + option, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "data":
            print(json.dumps(snapshot(), indent=2))
            return 0
        paths = [path.resolve() for path in (args.json, args.html, args.markdown) if path]
        if len(set(paths)) != len(paths) or args.scenario.resolve() in paths:
            raise ValueError(
                "Output paths must be distinct and cannot overwrite the input scenario"
            )
        document = build_document(
            json.loads(args.scenario.read_text()), samples=args.samples, seed=args.seed
        )
        serialized = json.dumps(document, indent=2, allow_nan=False) + "\n"
        outputs = [
            (args.json, serialized),
            (args.html, html_report(document)),
            (args.markdown, markdown_report(document)),
        ]
        for path, content in outputs:
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        print(
            serialized
            if not paths
            else json.dumps(
                {
                    "assessment_activity_mbq": document["result"]["assessment_activity_mbq"],
                    "latest_start": document["result"]["latest_start"],
                    "probability_miss": document["monte_carlo"]["probability_miss"],
                    "outputs": [str(path) for path, _ in outputs if path],
                },
                indent=2,
            )
        )
        return 0
    except (ValueError, TypeError, OSError, OverflowError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

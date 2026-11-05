"""Rebuild the committed studies or verify they still reproduce from the pinned inputs."""

import argparse
import json
import sys
from pathlib import Path

from batch_timing.report import build_document, html_report, markdown_report

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if saved reports differ")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    stale = []
    summary = {}
    for name in ("f18", "ac225"):
        config = json.loads((ROOT / "examples" / f"{name}.json").read_text())
        doc = build_document(config, samples=20000, seed=2026)
        contents = {
            "json": json.dumps(doc, indent=2, allow_nan=False) + "\n",
            "md": markdown_report(doc),
            "html": html_report(doc),
        }
        for suffix, content in contents.items():
            path = args.output_dir / f"{name}.{suffix}"
            if args.check:
                if not path.exists() or path.read_text(encoding="utf-8") != content:
                    stale.append(path.name)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        summary[name] = {
            key: doc["result"][key] for key in ("assessment_activity_mbq", "latest_start")
        }
        summary[name].update(
            {
                key: doc["monte_carlo"][key]
                for key in ("samples", "misses", "probability_miss", "wilson_95_interval")
            }
        )
    if stale:
        print("Stale or missing reports: " + ", ".join(stale), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    if args.check:
        print("All six saved report files reproduce.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

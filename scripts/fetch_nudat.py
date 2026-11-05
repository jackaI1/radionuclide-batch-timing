#!/usr/bin/env python3
"""Pin only the ground-state fields used here from the public NuDat chart data."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

URL = "https://www.nndc.bnl.gov/nudat3/data/output.json"
NAMES = [
    "18F",
    "68Ga",
    "64Cu",
    "177Lu",
    "225Ac",
    "221Fr",
    "217At",
    "213Bi",
    "213Po",
    "209Tl",
    "209Pb",
    "209Bi",
]


def extract(raw, retrieved):
    dataset = json.loads(raw)
    index = {row["name"]: row for row in dataset["nuclides"]}
    selected = {}
    for name in NAMES:
        ground = [level for level in index[name]["levels"] if level["energy"]["value"] == 0]
        if len(ground) != 1:
            raise ValueError(f"{name}: expected exactly one ground state")
        level = ground[0]
        selected[name] = {key: level[key] for key in ("energy", "halflife", "decayModes")}
    return {
        "source": URL,
        "retrieved_utc": retrieved,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "ground_states": selected,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Use a previously downloaded full NuDat JSON")
    parser.add_argument(
        "--output", type=Path, default=Path("src/batch_timing/data/nudat_snapshot.json")
    )
    args = parser.parse_args()
    if args.source:
        raw = args.source.read_bytes()
    else:
        with urlopen(URL, timeout=60) as response:
            raw = response.read()
    snapshot = extract(raw, datetime.now(UTC).isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(f"Saved {len(snapshot['ground_states'])} ground states to {args.output}")
    print(f"Full source SHA-256: {snapshot['source_sha256']}")


if __name__ == "__main__":
    main()

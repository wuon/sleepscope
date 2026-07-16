#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sleep_analyzer.inference.emit import infer_and_write, infer_sleepscope_epochs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Infer SleepScope stage epochs from a phone-sensor prototype CSV "
            "(accel, gyro, mic dB)."
        )
    )
    parser.add_argument(
        "csv",
        type=Path,
        help="Prototype sensor CSV with # metadata headers and Timestamp/IMU/dB/Event columns",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Write SleepScope-shaped epoch JSON to this path",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        epochs = infer_sleepscope_epochs(args.csv)
        path = infer_and_write(args.csv, args.out)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    stage_counts: dict[str, int] = {}
    for epoch in epochs:
        stage_counts[epoch["state"]] = stage_counts.get(epoch["state"], 0) + 1

    print(f"Wrote {len(epochs)} epoch(s) to {path}")
    for state in ("Awake", "Light", "Deep", "REM"):
        count = stage_counts.get(state, 0)
        minutes = count * 2.0
        print(f"  {state}: {count} epochs ({minutes:.0f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sleep_analyzer.inference.emit import infer_and_write, infer_phone_stages_from_csv
from sleep_analyzer.timeline import BinaryLabel, PhoneStage, collapse_phone_timeline, minutes_for_label


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Infer 30s Awake/Restless/QuietSleep stages from a SleepScope sensor CSV, "
            "then collapse to Sleep/Awake for comparison."
        )
    )
    parser.add_argument("csv", type=Path, help="Prototype sensor CSV")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Write phone-stage epoch JSON to this path",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        timeline = infer_phone_stages_from_csv(args.csv)
        path = infer_and_write(args.csv, args.out)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    counts = Counter(epoch.label for epoch in timeline.epochs)
    binary = collapse_phone_timeline(timeline)
    asleep = minutes_for_label(binary, BinaryLabel.SLEEP.value)
    awake = minutes_for_label(binary, BinaryLabel.AWAKE.value)

    print(f"Wrote {len(timeline)} epoch(s) to {path}")
    for stage in (
        PhoneStage.AWAKE.value,
        PhoneStage.RESTLESS.value,
        PhoneStage.QUIET_SLEEP.value,
    ):
        count = counts.get(stage, 0)
        print(f"  {stage}: {count} bins ({count * 0.5:.1f} min)")
    print(f"  Binary → Sleep {asleep:.1f} min · Awake {awake:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

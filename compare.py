#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sleep_analyzer.compare import compare_many, discover_inputs
from sleep_analyzer.report import (
    format_console_report,
    write_comparison_timelines,
    write_hypnogram_plots,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare SleepScope vs Fitbit Sleep/Awake timelines and write a "
            "condensed hypnogram."
        )
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Night manifest JSON, experiment index JSON, or directory of night manifests",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Directory for the two timeline JSON outputs (SleepScope + Fitbit)",
    )
    parser.add_argument(
        "--plots",
        type=Path,
        help="Directory for condensed Awake/Sleep comparison hypnograms",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        manifest_paths = discover_inputs(args.input)
        comparisons = compare_many(manifest_paths)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not comparisons:
        print("No comparisons produced.", file=sys.stderr)
        return 1

    print(format_console_report(comparisons), end="")

    if args.out:
        written = write_comparison_timelines(comparisons, args.out)
        for path in written:
            print(f"Wrote timeline: {path}")
    if args.plots:
        plots = write_hypnogram_plots(comparisons, args.plots)
        for path in plots:
            print(f"Wrote hypnogram: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

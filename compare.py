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
    rollup_by_provider,
    write_csv,
    write_plots,
    write_rollup_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare SleepScope session metrics against a wearable "
            "(Fitbit in v1) using night manifests."
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
        help="Write per-night comparison CSV to this path",
    )
    parser.add_argument(
        "--rollup-out",
        type=Path,
        help="Write provider rollup CSV to this path",
    )
    parser.add_argument(
        "--plots",
        type=Path,
        help="Directory for scatter and Bland-Altman plots (deep_min, rem_min, efficiency)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        manifest_paths = discover_inputs(args.input)
        deltas = compare_many(manifest_paths)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not deltas:
        print("No comparisons produced.", file=sys.stderr)
        return 1

    rollups = rollup_by_provider(deltas)
    print(format_console_report(deltas, rollups), end="")

    if args.out:
        write_csv(deltas, args.out)
        print(f"Wrote per-night CSV: {args.out}")
    if args.rollup_out:
        write_rollup_csv(rollups, args.rollup_out)
        print(f"Wrote rollup CSV: {args.rollup_out}")
    if args.plots:
        written = write_plots(deltas, args.plots)
        print(f"Wrote {len(written)} plot(s) to {args.plots}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

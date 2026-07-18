from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sleep_analyzer.inference.csv_parser import parse_sensor_csv
from sleep_analyzer.inference.phone import infer_phone_timeline
from sleep_analyzer.timeline import EpochTimeline, collapse_phone_timeline


def infer_phone_stages_from_csv(path: Path | str) -> EpochTimeline:
    recording = parse_sensor_csv(path)
    timeline, _bins = infer_phone_timeline(recording)
    return timeline


def infer_binary_timeline_from_csv(path: Path | str) -> EpochTimeline:
    return collapse_phone_timeline(infer_phone_stages_from_csv(path))


def timeline_to_json_rows(timeline: EpochTimeline) -> list[dict[str, str]]:
    return [
        {
            "timestamp": _format_timestamp(epoch.start),
            "state": epoch.label,
        }
        for epoch in timeline.epochs
    ]


def write_timeline_json(timeline: EpochTimeline, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(timeline_to_json_rows(timeline), handle, indent=2)
        handle.write("\n")
    return path


def infer_and_write(csv_path: Path | str, out_path: Path | str) -> Path:
    timeline = infer_phone_stages_from_csv(csv_path)
    return write_timeline_json(timeline, out_path)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    utc = value.astimezone(timezone.utc)
    text = utc.isoformat(timespec="milliseconds")
    return text.replace("+00:00", "Z")

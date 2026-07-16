from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sleep_analyzer.inference.classify import StageEpoch, classify_epochs
from sleep_analyzer.inference.csv_parser import parse_sensor_csv
from sleep_analyzer.inference.features import extract_epoch_features


def infer_sleepscope_epochs(path: Path | str) -> list[dict[str, str]]:
    """Parse a prototype sensor CSV and return SleepScope-shaped epoch dicts."""
    recording = parse_sensor_csv(path)
    features = extract_epoch_features(recording)
    stages = classify_epochs(features)
    return epochs_to_sleepscope(stages)


def epochs_to_sleepscope(epochs: list[StageEpoch]) -> list[dict[str, str]]:
    return [
        {
            "timestamp": _format_timestamp(epoch.timestamp),
            "state": epoch.state,
        }
        for epoch in epochs
    ]


def write_sleepscope_json(epochs: list[dict[str, str]], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(epochs, handle, indent=2)
        handle.write("\n")
    return path


def infer_and_write(csv_path: Path | str, out_path: Path | str) -> Path:
    epochs = infer_sleepscope_epochs(csv_path)
    return write_sleepscope_json(epochs, out_path)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    utc = value.astimezone(timezone.utc)
    # Match SleepScope-style Zulu timestamps with millis when present.
    text = utc.isoformat(timespec="milliseconds")
    return text.replace("+00:00", "Z")

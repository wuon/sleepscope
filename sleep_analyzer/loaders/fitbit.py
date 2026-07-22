from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sleep_analyzer.loaders.base import register_loader
from sleep_analyzer.metrics import build_binary_session
from sleep_analyzer.models import BinarySession
from sleep_analyzer.timeline import (
    BinaryLabel,
    Epoch,
    EpochTimeline,
    Interval,
    paint_binary_from_wearable_intervals,
    wearable_to_binary,
)


class FitbitLoader:
    name = "fitbit"

    def load(self, path: Path, *, day: str | None = None) -> BinarySession:
        del day  # unused; shared loader signature with multi-day providers
        path = Path(path)
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        sleep_log = _extract_main_sleep_log(payload, path)
        intervals = _intervals_from_levels_data(sleep_log)
        if intervals:
            timeline = paint_binary_from_wearable_intervals(intervals)
            return build_binary_session(
                provider=self.name,
                timeline=timeline,
                binary=True,
            )

        return _session_from_summary(sleep_log, path)


def _extract_main_sleep_log(payload: Any, path: Path) -> dict[str, Any]:
    if isinstance(payload, dict) and "sleep" in payload:
        logs = payload["sleep"]
        if not isinstance(logs, list) or not logs:
            raise ValueError(f"{path}: 'sleep' array is empty")
        return _select_main_sleep(logs, path)

    if isinstance(payload, list):
        if not payload:
            raise ValueError(f"{path}: Fitbit export array is empty")
        return _select_main_sleep(payload, path)

    if isinstance(payload, dict) and (
        "startTime" in payload or "levels" in payload or "minutesAsleep" in payload
    ):
        return payload

    raise ValueError(
        f"{path}: unrecognized Fitbit sleep JSON. Expected a sleep log object, "
        "a list of logs, or {'sleep': [...]}."
    )


def _is_main_sleep(item: dict[str, Any]) -> bool:
    if "isMainSleep" in item:
        return bool(item["isMainSleep"])
    if "mainSleep" in item:
        return bool(item["mainSleep"])
    return False


def _select_main_sleep(logs: list[Any], path: Path) -> dict[str, Any]:
    typed = [item for item in logs if isinstance(item, dict)]
    if not typed:
        raise ValueError(f"{path}: sleep log entry must be an object")

    mains = [item for item in typed if _is_main_sleep(item)]
    candidates = mains or typed

    def sort_key(item: dict[str, Any]) -> str:
        return str(item.get("startTime") or item.get("dateOfSleep") or "")

    return max(candidates, key=sort_key)


def _intervals_from_levels_data(sleep_log: dict[str, Any]) -> list[Interval]:
    levels = sleep_log.get("levels")
    if not isinstance(levels, dict):
        return []
    data = levels.get("data")
    if not isinstance(data, list) or not data:
        return []

    intervals: list[Interval] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        level = entry.get("level")
        seconds = entry.get("seconds")
        date_time = entry.get("dateTime")
        if level is None or seconds is None or date_time is None:
            continue
        start = _parse_fitbit_datetime(date_time, Path("."), field="dateTime")
        end = start + timedelta(seconds=float(seconds))
        intervals.append(Interval(start=start, end=end, label=str(level)))
    return intervals


def _session_from_summary(sleep_log: dict[str, Any], path: Path) -> BinarySession:
    """Fallback when levels.data is missing: paint contiguous awake/sleep from totals."""
    start = _parse_fitbit_datetime(
        sleep_log.get("startTime") or sleep_log.get("startDate"),
        path,
        field="startTime",
    )
    end = _parse_fitbit_datetime(
        sleep_log.get("endTime") or sleep_log.get("endDate"),
        path,
        field="endTime",
    )

    asleep = 0.0
    awake = 0.0
    levels = sleep_log.get("levels")
    if isinstance(levels, dict) and isinstance(levels.get("summary"), dict):
        for key, value in levels["summary"].items():
            minutes = _summary_minutes(value)
            if wearable_to_binary(str(key)) == BinaryLabel.SLEEP:
                asleep += minutes
            else:
                awake += minutes
    elif "minutesAsleep" in sleep_log or "minutesAwake" in sleep_log:
        asleep = float(sleep_log.get("minutesAsleep") or 0)
        awake = float(sleep_log.get("minutesAwake") or 0)
    else:
        raise ValueError(
            f"{path}: Fitbit sleep log missing levels.data and usable summary totals"
        )

    # Simple contiguous layout: initial awake minutes, then sleep, then trailing awake.
    epochs: list[Epoch] = []
    cursor = start
    for _ in range(int(round(awake * 2))):
        epochs.append(Epoch(start=cursor, label=BinaryLabel.AWAKE.value))
        cursor = cursor + timedelta(seconds=30)
    for _ in range(int(round(asleep * 2))):
        epochs.append(Epoch(start=cursor, label=BinaryLabel.SLEEP.value))
        cursor = cursor + timedelta(seconds=30)
    while cursor < end:
        epochs.append(Epoch(start=cursor, label=BinaryLabel.AWAKE.value))
        cursor = cursor + timedelta(seconds=30)
    if not epochs:
        raise ValueError(f"{path}: could not build Fitbit timeline from summary")

    return build_binary_session(
        provider="fitbit",
        timeline=EpochTimeline(epochs=epochs, provider="fitbit"),
        binary=True,
    )


def _summary_minutes(value: Any) -> float:
    if isinstance(value, dict):
        if "minutes" in value:
            return float(value["minutes"])
        if "seconds" in value:
            return float(value["seconds"]) / 60.0
    return float(value)


def _parse_fitbit_datetime(value: Any, path: Path, *, field: str) -> datetime:
    if value is None:
        raise ValueError(f"{path}: Fitbit sleep log missing '{field}'")
    if not isinstance(value, str):
        raise ValueError(f"{path}: Fitbit '{field}' must be a string")
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        raise ValueError(f"{path}: invalid Fitbit datetime for '{field}': {value}") from None


register_loader(FitbitLoader())

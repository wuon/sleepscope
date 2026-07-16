from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sleep_analyzer.loaders.base import register_loader
from sleep_analyzer.metrics import build_session_metrics
from sleep_analyzer.models import SessionMetrics

FITBIT_STAGE_MAP = {
    "deep": "deep",
    "light": "light",
    "rem": "rem",
    "wake": "awake",
    "awake": "awake",
    "asleep": "light",  # classic sleep logs
    "restless": "light",
}


class FitbitLoader:
    name = "fitbit"

    def load(self, path: Path) -> SessionMetrics:
        path = Path(path)
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        sleep_log = _extract_main_sleep_log(payload, path)
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

        stage_minutes = _stage_minutes_from_log(sleep_log)
        duration = _duration_minutes(sleep_log, start, end, stage_minutes)

        return build_session_metrics(
            provider=self.name,
            start=start,
            end=end,
            deep_min=stage_minutes["deep"],
            light_min=stage_minutes["light"],
            rem_min=stage_minutes["rem"],
            awake_min=stage_minutes["awake"],
            duration_min=duration,
        )


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
    # Google Takeout uses mainSleep; Web API uses isMainSleep.
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

    # Prefer the most recent main sleep when a Takeout file contains many nights.
    return max(candidates, key=sort_key)


def _stage_minutes_from_log(sleep_log: dict[str, Any]) -> dict[str, float]:
    stages = {"deep": 0.0, "light": 0.0, "rem": 0.0, "awake": 0.0}
    levels = sleep_log.get("levels")

    if isinstance(levels, dict):
        summary = levels.get("summary")
        if isinstance(summary, dict) and summary:
            for key, value in summary.items():
                canonical = FITBIT_STAGE_MAP.get(str(key).lower())
                if canonical is None:
                    continue
                minutes = _summary_minutes(value)
                stages[canonical] += minutes
            if any(stages.values()):
                return stages

        data = levels.get("data")
        if isinstance(data, list):
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                level = str(entry.get("level", "")).lower()
                canonical = FITBIT_STAGE_MAP.get(level)
                if canonical is None:
                    continue
                seconds = entry.get("seconds")
                if seconds is None:
                    continue
                stages[canonical] += float(seconds) / 60.0
            if any(stages.values()):
                return stages

    # Top-level summary fields used by some exports / API responses.
    if "SleepLevelDeep" in sleep_log or "minutesAsleep" in sleep_log:
        stages["deep"] = float(sleep_log.get("SleepLevelDeep") or sleep_log.get("deep") or 0)
        stages["light"] = float(
            sleep_log.get("SleepLevelLight")
            or sleep_log.get("light")
            or sleep_log.get("SleepLevelAsleep")
            or 0
        )
        stages["rem"] = float(sleep_log.get("SleepLevelRem") or sleep_log.get("rem") or 0)
        stages["awake"] = float(
            sleep_log.get("SleepLevelWake")
            or sleep_log.get("SleepLevelAwake")
            or sleep_log.get("minutesAwake")
            or 0
        )
        if any(stages.values()):
            return stages

    raise ValueError("Fitbit sleep log is missing levels.summary, levels.data, and stage totals")


def _summary_minutes(value: Any) -> float:
    if isinstance(value, dict):
        if "minutes" in value:
            return float(value["minutes"])
        if "seconds" in value:
            return float(value["seconds"]) / 60.0
    return float(value)


def _duration_minutes(
    sleep_log: dict[str, Any],
    start: datetime,
    end: datetime,
    stage_minutes: dict[str, float],
) -> float:
    if "timeInBed" in sleep_log and sleep_log["timeInBed"] is not None:
        return float(sleep_log["timeInBed"])
    if "duration" in sleep_log and sleep_log["duration"] is not None:
        # Fitbit Web API duration is milliseconds.
        duration = float(sleep_log["duration"])
        if duration > 10_000:
            return duration / 60_000.0
        return duration / 60.0
    span = (end - start).total_seconds() / 60.0
    if span > 0:
        return span
    return sum(stage_minutes.values())


def _parse_fitbit_datetime(value: Any, path: Path, *, field: str) -> datetime:
    if value is None:
        raise ValueError(f"{path}: Fitbit sleep log missing '{field}'")
    if not isinstance(value, str):
        raise ValueError(f"{path}: Fitbit '{field}' must be a string")
    text = value.strip().replace("Z", "+00:00")
    # Fitbit often omits timezone; treat naive as local-wall / UTC-comparable naive→UTC.
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"{path}: invalid Fitbit datetime for '{field}': {value}") from None
    return parsed


register_loader(FitbitLoader())

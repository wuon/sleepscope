from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from sleep_analyzer.loaders.base import register_loader
from sleep_analyzer.metrics import build_binary_session
from sleep_analyzer.models import BinarySession
from sleep_analyzer.timeline import Interval, paint_binary_from_wearable_intervals

SLEEP_ANALYSIS_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"

# HealthKit category values → short wearable stage tokens.
_APPLE_VALUE_TO_STAGE = {
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",
    "HKCategoryValueSleepAnalysisAsleep": "asleep",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisInBed": "inbed",
}

_STAGE_RECORDS = frozenset({"core", "deep", "rem", "asleep", "awake"})


class AppleWatchLoader:
    name = "apple_watch"

    def load(self, path: Path, *, day: str | None = None) -> BinarySession:
        del day  # unused; shared loader signature with multi-day providers
        path = Path(path)
        intervals = _parse_sleep_intervals(path)
        if not intervals:
            raise ValueError(
                f"{path}: no HKCategoryTypeIdentifierSleepAnalysis records found"
            )

        timeline = paint_binary_from_wearable_intervals(intervals)
        return build_binary_session(
            provider=self.name,
            timeline=timeline,
            binary=True,
        )


def _parse_sleep_intervals(path: Path) -> list[Interval]:
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ValueError(f"{path}: invalid Apple Health XML export ({exc})") from exc

    raw: list[Interval] = []
    for element in tree.getroot().iter("Record"):
        if element.get("type") != SLEEP_ANALYSIS_TYPE:
            continue
        value = element.get("value")
        start_raw = element.get("startDate")
        end_raw = element.get("endDate")
        if not value or not start_raw or not end_raw:
            continue
        stage = _APPLE_VALUE_TO_STAGE.get(value)
        if stage is None:
            # Unknown sleep category — keep raw token for wearable_to_binary fallback.
            stage = value
        start = _parse_apple_datetime(start_raw, path, field="startDate")
        end = _parse_apple_datetime(end_raw, path, field="endDate")
        if end <= start:
            continue
        raw.append(Interval(start=start, end=end, label=stage))

    if not raw:
        return []

    # Prefer stage/awake samples; InBed often wraps the whole night and overlaps them.
    staged = [item for item in raw if item.label in _STAGE_RECORDS]
    if staged:
        return staged

    # InBed-only export: treat time-in-bed as a coarse Sleep proxy.
    return [
        Interval(
            start=item.start,
            end=item.end,
            label="asleep" if item.label == "inbed" else item.label,
        )
        for item in raw
    ]


def _parse_apple_datetime(value: str, path: Path, *, field: str) -> datetime:
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S.%f %z"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"{path}: invalid Apple Health datetime for '{field}': {value}")


register_loader(AppleWatchLoader())

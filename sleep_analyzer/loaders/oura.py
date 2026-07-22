from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sleep_analyzer.loaders.base import register_loader
from sleep_analyzer.metrics import build_binary_session
from sleep_analyzer.models import BinarySession
from sleep_analyzer.timeline import Interval, paint_binary_from_wearable_intervals

# Oura sleep_phase_30_sec / sleep_phase_5_min digit codes.
_OURA_PHASE_TO_STAGE = {
    "1": "deep",
    "2": "light",
    "3": "rem",
    "4": "awake",
}

_PHASE_SECONDS = {
    "sleep_phase_30_sec": 30,
    "sleep_phase_5_min": 5 * 60,
}


class OuraLoader:
    name = "oura"

    def load(self, path: Path, *, day: str | None = None) -> BinarySession:
        path = Path(path)
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        sessions = _extract_sleep_sessions(payload, path)
        selected = _select_sessions_for_day(sessions, path, day=day)
        intervals = _intervals_from_sessions(selected, path)
        if not intervals:
            raise ValueError(f"{path}: no usable Oura sleep phase samples found")

        timeline = paint_binary_from_wearable_intervals(intervals)
        return build_binary_session(
            provider=self.name,
            timeline=timeline,
            binary=True,
        )


def _extract_sleep_sessions(payload: Any, path: Path) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        raw = payload["data"]
    elif isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict) and (
        "sleep_phase_30_sec" in payload or "bedtime_start" in payload
    ):
        raw = [payload]
    else:
        raise ValueError(
            f"{path}: unrecognized Oura sleep JSON. Expected "
            "{'data': [...]} , a list of sleep objects, or one sleep object."
        )

    sessions = [item for item in raw if isinstance(item, dict)]
    if not sessions:
        raise ValueError(f"{path}: Oura sleep data is empty")
    return sessions


def _select_sessions_for_day(
    sessions: list[dict[str, Any]],
    path: Path,
    *,
    day: str | None,
) -> list[dict[str, Any]]:
    if day is not None:
        matched = [item for item in sessions if str(item.get("day") or "") == day]
        if not matched:
            available = sorted(
                {str(item.get("day")) for item in sessions if item.get("day")}
            )
            raise ValueError(
                f"{path}: no Oura sleep sessions for day={day!r}. "
                f"Available days: {', '.join(available) or '(none)'}"
            )
        return matched

    days = sorted({str(item.get("day")) for item in sessions if item.get("day")})
    if len(days) > 1:
        raise ValueError(
            f"{path}: Oura export spans multiple days ({', '.join(days)}). "
            "Set comparisons[].day to select one wake day."
        )
    return sessions


def _intervals_from_sessions(
    sessions: list[dict[str, Any]], path: Path
) -> list[Interval]:
    intervals: list[Interval] = []
    for session in sessions:
        intervals.extend(_intervals_from_session(session, path))
    intervals.sort(key=lambda item: item.start)
    return intervals


def _intervals_from_session(session: dict[str, Any], path: Path) -> list[Interval]:
    start = _parse_oura_datetime(
        session.get("bedtime_start"), path, field="bedtime_start"
    )
    phases, step_seconds = _phase_samples(session, path)
    if not phases:
        return []

    intervals: list[Interval] = []
    run_label: str | None = None
    run_start = start
    cursor = start

    for digit in phases:
        stage = _OURA_PHASE_TO_STAGE.get(digit)
        if stage is None:
            raise ValueError(
                f"{path}: unknown Oura sleep phase code {digit!r} "
                "(expected 1=deep, 2=light, 3=rem, 4=awake)"
            )
        if run_label is None:
            run_label = stage
            run_start = cursor
        elif stage != run_label:
            intervals.append(Interval(start=run_start, end=cursor, label=run_label))
            run_label = stage
            run_start = cursor
        cursor = cursor + timedelta(seconds=step_seconds)

    if run_label is not None and cursor > run_start:
        intervals.append(Interval(start=run_start, end=cursor, label=run_label))
    return intervals


def _phase_samples(session: dict[str, Any], path: Path) -> tuple[str, int]:
    for key, seconds in _PHASE_SECONDS.items():
        raw = session.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip(), seconds
    raise ValueError(
        f"{path}: Oura sleep session missing sleep_phase_30_sec / sleep_phase_5_min"
    )


def _parse_oura_datetime(value: Any, path: Path, *, field: str) -> datetime:
    if value is None:
        raise ValueError(f"{path}: Oura sleep session missing '{field}'")
    if not isinstance(value, str):
        raise ValueError(f"{path}: Oura '{field}' must be a string")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{path}: invalid Oura datetime for '{field}': {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError(
            f"{path}: Oura '{field}' must include a timezone offset, got '{value}'"
        )
    return parsed


register_loader(OuraLoader())

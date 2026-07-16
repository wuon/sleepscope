from __future__ import annotations

from datetime import datetime, timezone

from sleep_analyzer.models import NightDelta, SessionMetrics


EPOCH_MINUTES = 2.0


def build_session_metrics(
    *,
    provider: str,
    start: datetime,
    end: datetime,
    deep_min: float,
    light_min: float,
    rem_min: float,
    awake_min: float,
    duration_min: float | None = None,
) -> SessionMetrics:
    duration = duration_min if duration_min is not None else (end - start).total_seconds() / 60.0
    if duration <= 0:
        raise ValueError(f"{provider}: duration_min must be positive, got {duration}")

    asleep = deep_min + light_min + rem_min
    return SessionMetrics(
        provider=provider,
        start=_ensure_aware(start),
        end=_ensure_aware(end),
        duration_min=float(duration),
        deep_min=float(deep_min),
        light_min=float(light_min),
        rem_min=float(rem_min),
        awake_min=float(awake_min),
        asleep_min=float(asleep),
        efficiency=float(asleep / duration) if duration else 0.0,
    )


def compare_sessions(
    reference: SessionMetrics,
    comparison: SessionMetrics,
    *,
    night_id: str,
    date: str | None = None,
    notes: str | None = None,
) -> NightDelta:
    return NightDelta(
        night_id=night_id,
        date=date,
        comparison_provider=comparison.provider,
        reference=reference,
        comparison=comparison,
        duration_min_delta=reference.duration_min - comparison.duration_min,
        deep_min_delta=reference.deep_min - comparison.deep_min,
        light_min_delta=reference.light_min - comparison.light_min,
        rem_min_delta=reference.rem_min - comparison.rem_min,
        awake_min_delta=reference.awake_min - comparison.awake_min,
        asleep_min_delta=reference.asleep_min - comparison.asleep_min,
        efficiency_delta=reference.efficiency - comparison.efficiency,
        deep_pct_delta=reference.stage_pct("deep") - comparison.stage_pct("deep"),
        light_pct_delta=reference.stage_pct("light") - comparison.stage_pct("light"),
        rem_pct_delta=reference.stage_pct("rem") - comparison.stage_pct("rem"),
        awake_pct_delta=reference.stage_pct("awake") - comparison.stage_pct("awake"),
        start_abs_min_delta=abs((reference.start - comparison.start).total_seconds()) / 60.0,
        end_abs_min_delta=abs((reference.end - comparison.end).total_seconds()) / 60.0,
        notes=notes,
    )


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

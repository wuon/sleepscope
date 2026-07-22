from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sleep_analyzer.timeline import BinaryLabel, EpochTimeline, minutes_for_label


@dataclass(frozen=True)
class BinarySession:
    """Provider sleep/wake timeline (30s epochs) plus simple minute totals."""

    provider: str
    timeline: EpochTimeline

    @property
    def start(self) -> datetime:
        if not self.timeline.epochs:
            raise ValueError(f"{self.provider}: empty timeline")
        return self.timeline.start  # type: ignore[return-value]

    @property
    def end(self) -> datetime:
        if not self.timeline.epochs:
            raise ValueError(f"{self.provider}: empty timeline")
        return self.timeline.end  # type: ignore[return-value]

    @property
    def duration_min(self) -> float:
        return len(self.timeline) * 0.5

    @property
    def asleep_min(self) -> float:
        return minutes_for_label(self.timeline, BinaryLabel.SLEEP.value)

    @property
    def awake_min(self) -> float:
        return minutes_for_label(self.timeline, BinaryLabel.AWAKE.value)

    def to_timeline_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for epoch in self.timeline.epochs:
            start = epoch.start
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            text = start.astimezone(timezone.utc).isoformat(timespec="milliseconds")
            rows.append(
                {
                    "timestamp": text.replace("+00:00", "Z"),
                    "state": epoch.label,
                }
            )
        return rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_min": self.duration_min,
            "asleep_min": self.asleep_min,
            "awake_min": self.awake_min,
            "epochs": self.to_timeline_rows(),
        }


@dataclass(frozen=True)
class NightComparison:
    """Paired SleepScope vs Fitbit binary timelines for one night."""

    night_id: str
    reference: BinarySession
    comparison: BinarySession
    date: str | None = None
    notes: str | None = None

    @property
    def comparison_provider(self) -> str:
        return self.comparison.provider


@dataclass(frozen=True)
class DataSource:
    provider: str
    path: str
    # Optional wake-day filter (YYYY-MM-DD) for multi-day exports (e.g. Oura).
    day: str | None = None


@dataclass(frozen=True)
class NightManifest:
    id: str
    reference: DataSource
    comparisons: tuple[DataSource, ...]
    date: str | None = None
    notes: str | None = None
    path: str | None = None

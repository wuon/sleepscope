from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


CANONICAL_STAGES = ("deep", "light", "rem", "awake")


@dataclass(frozen=True)
class SessionMetrics:
    """Normalized session-level sleep metrics shared across providers."""

    provider: str
    start: datetime
    end: datetime
    duration_min: float
    deep_min: float
    light_min: float
    rem_min: float
    awake_min: float
    asleep_min: float
    efficiency: float

    def stage_pct(self, stage: str) -> float:
        if self.duration_min <= 0:
            return 0.0
        value = getattr(self, f"{stage}_min")
        return 100.0 * value / self.duration_min

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["start"] = self.start.isoformat()
        payload["end"] = self.end.isoformat()
        for stage in CANONICAL_STAGES:
            payload[f"{stage}_pct"] = self.stage_pct(stage)
        return payload


@dataclass(frozen=True)
class NightDelta:
    """Per-night SleepScope − wearable deltas for shared metrics."""

    night_id: str
    date: str | None
    comparison_provider: str
    reference: SessionMetrics
    comparison: SessionMetrics
    duration_min_delta: float
    deep_min_delta: float
    light_min_delta: float
    rem_min_delta: float
    awake_min_delta: float
    asleep_min_delta: float
    efficiency_delta: float
    deep_pct_delta: float
    light_pct_delta: float
    rem_pct_delta: float
    awake_pct_delta: float
    start_abs_min_delta: float
    end_abs_min_delta: float
    notes: str | None = None

    def to_row(self) -> dict[str, Any]:
        return {
            "night_id": self.night_id,
            "date": self.date,
            "comparison_provider": self.comparison_provider,
            "notes": self.notes,
            "ref_provider": self.reference.provider,
            "ref_start": self.reference.start.isoformat(),
            "ref_end": self.reference.end.isoformat(),
            "ref_duration_min": self.reference.duration_min,
            "ref_deep_min": self.reference.deep_min,
            "ref_light_min": self.reference.light_min,
            "ref_rem_min": self.reference.rem_min,
            "ref_awake_min": self.reference.awake_min,
            "ref_asleep_min": self.reference.asleep_min,
            "ref_efficiency": self.reference.efficiency,
            "cmp_provider": self.comparison.provider,
            "cmp_start": self.comparison.start.isoformat(),
            "cmp_end": self.comparison.end.isoformat(),
            "cmp_duration_min": self.comparison.duration_min,
            "cmp_deep_min": self.comparison.deep_min,
            "cmp_light_min": self.comparison.light_min,
            "cmp_rem_min": self.comparison.rem_min,
            "cmp_awake_min": self.comparison.awake_min,
            "cmp_asleep_min": self.comparison.asleep_min,
            "cmp_efficiency": self.comparison.efficiency,
            "duration_min_delta": self.duration_min_delta,
            "deep_min_delta": self.deep_min_delta,
            "light_min_delta": self.light_min_delta,
            "rem_min_delta": self.rem_min_delta,
            "awake_min_delta": self.awake_min_delta,
            "asleep_min_delta": self.asleep_min_delta,
            "efficiency_delta": self.efficiency_delta,
            "deep_pct_delta": self.deep_pct_delta,
            "light_pct_delta": self.light_pct_delta,
            "rem_pct_delta": self.rem_pct_delta,
            "awake_pct_delta": self.awake_pct_delta,
            "start_abs_min_delta": self.start_abs_min_delta,
            "end_abs_min_delta": self.end_abs_min_delta,
        }


@dataclass(frozen=True)
class MetricRollup:
    metric: str
    n: int
    mean_bias: float
    mae: float
    rmse: float
    pearson_r: float | None
    spearman_r: float | None
    exploratory: bool


@dataclass(frozen=True)
class DataSource:
    provider: str
    path: str


@dataclass(frozen=True)
class NightManifest:
    id: str
    reference: DataSource
    comparisons: tuple[DataSource, ...]
    date: str | None = None
    notes: str | None = None
    path: str | None = None

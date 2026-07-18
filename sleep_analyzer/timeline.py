from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Sequence


EPOCH_SECONDS = 30
EPOCH_MINUTES = EPOCH_SECONDS / 60.0


class BinaryLabel(str, Enum):
    SLEEP = "Sleep"
    AWAKE = "Awake"


class PhoneStage(str, Enum):
    AWAKE = "Awake"
    RESTLESS = "Restless"
    QUIET_SLEEP = "QuietSleep"


# Fitbit stage tokens → binary.
WEARABLE_SLEEP_STAGES = frozenset(
    {
        "deep",
        "light",
        "rem",
        "asleep",
        "restless",  # Fitbit classic restless → Sleep bucket
    }
)
WEARABLE_AWAKE_STAGES = frozenset(
    {
        "wake",
        "awake",
    }
)


@dataclass(frozen=True)
class Interval:
    """Half-open [start, end) labeled interval."""

    start: datetime
    end: datetime
    label: str

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"Interval end must be after start: {self.start} .. {self.end}")


@dataclass(frozen=True)
class Epoch:
    start: datetime
    label: str

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=EPOCH_SECONDS)


@dataclass
class EpochTimeline:
    """Fixed 30-second epoch grid."""

    epochs: list[Epoch]
    provider: str | None = None

    def __len__(self) -> int:
        return len(self.epochs)

    @property
    def start(self) -> datetime | None:
        return self.epochs[0].start if self.epochs else None

    @property
    def end(self) -> datetime | None:
        return self.epochs[-1].end if self.epochs else None

    def labels(self) -> list[str]:
        return [epoch.label for epoch in self.epochs]


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def floor_to_epoch(value: datetime) -> datetime:
    value = ensure_aware(value)
    epoch = int(value.timestamp())
    floored = epoch - (epoch % EPOCH_SECONDS)
    return datetime.fromtimestamp(floored, tz=timezone.utc).astimezone(value.tzinfo)


def wearable_to_binary(stage: str) -> BinaryLabel:
    key = stage.strip().lower().replace(" ", "").replace("_", "")
    if key == "sleep":
        return BinaryLabel.SLEEP
    if key == "awake":
        return BinaryLabel.AWAKE
    if key in WEARABLE_SLEEP_STAGES or key.startswith("asleep"):
        return BinaryLabel.SLEEP
    if key in WEARABLE_AWAKE_STAGES or key.endswith("awake"):
        return BinaryLabel.AWAKE
    return BinaryLabel.AWAKE


def phone_to_binary(stage: str | PhoneStage) -> BinaryLabel:
    value = stage.value if isinstance(stage, PhoneStage) else str(stage)
    if value in (PhoneStage.QUIET_SLEEP.value, PhoneStage.RESTLESS.value, "Quiet Sleep"):
        return BinaryLabel.SLEEP
    return BinaryLabel.AWAKE


def collapse_phone_timeline(timeline: EpochTimeline) -> EpochTimeline:
    return EpochTimeline(
        epochs=[
            Epoch(start=epoch.start, label=phone_to_binary(epoch.label).value)
            for epoch in timeline.epochs
        ],
        provider=timeline.provider,
    )


def resample_intervals(
    intervals: Sequence[Interval],
    *,
    grid_start: datetime | None = None,
    grid_end: datetime | None = None,
    default_label: str = BinaryLabel.AWAKE.value,
) -> EpochTimeline:
    """Paint half-open intervals onto a 30s grid (later intervals win on overlap)."""
    if not intervals:
        raise ValueError("intervals must be non-empty")

    starts = [ensure_aware(item.start) for item in intervals]
    ends = [ensure_aware(item.end) for item in intervals]
    start = floor_to_epoch(grid_start or min(starts))
    end_raw = ensure_aware(grid_end or max(ends))
    end = floor_to_epoch(end_raw)
    if end < end_raw:
        end = end + timedelta(seconds=EPOCH_SECONDS)

    labels: list[str] = []
    cursor = start
    while cursor < end:
        epoch_end = cursor + timedelta(seconds=EPOCH_SECONDS)
        label = default_label
        for interval in intervals:
            istart = ensure_aware(interval.start)
            iend = ensure_aware(interval.end)
            if istart < epoch_end and iend > cursor:
                label = interval.label
        labels.append(label)
        cursor = epoch_end

    return EpochTimeline(
        epochs=[
            Epoch(start=start + timedelta(seconds=EPOCH_SECONDS * index), label=label)
            for index, label in enumerate(labels)
        ]
    )


def paint_binary_from_wearable_intervals(intervals: Sequence[Interval]) -> EpochTimeline:
    binary_intervals = [
        Interval(
            start=item.start,
            end=item.end,
            label=wearable_to_binary(item.label).value,
        )
        for item in intervals
    ]
    return resample_intervals(binary_intervals)


def minutes_for_label(timeline: EpochTimeline, label: str) -> float:
    return sum(1 for epoch in timeline.epochs if epoch.label == label) * EPOCH_MINUTES

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sleep_analyzer.timeline import (
    BinaryLabel,
    Epoch,
    EpochTimeline,
    Interval,
    PhoneStage,
    collapse_phone_timeline,
    paint_binary_from_wearable_intervals,
    phone_to_binary,
    wearable_to_binary,
)


def test_wearable_and_phone_binary_mapping():
    assert wearable_to_binary("deep") == BinaryLabel.SLEEP
    assert wearable_to_binary("light") == BinaryLabel.SLEEP
    assert wearable_to_binary("rem") == BinaryLabel.SLEEP
    assert wearable_to_binary("core") == BinaryLabel.SLEEP
    assert wearable_to_binary("restless") == BinaryLabel.SLEEP
    assert wearable_to_binary("wake") == BinaryLabel.AWAKE
    assert wearable_to_binary("awake") == BinaryLabel.AWAKE
    assert phone_to_binary(PhoneStage.RESTLESS) == BinaryLabel.SLEEP
    assert phone_to_binary(PhoneStage.QUIET_SLEEP) == BinaryLabel.SLEEP
    assert phone_to_binary(PhoneStage.AWAKE) == BinaryLabel.AWAKE


def test_resample_intervals_to_30s():
    start = datetime(2026, 7, 12, 1, 0, tzinfo=timezone.utc)
    intervals = [
        Interval(start, start + timedelta(minutes=10), "wake"),
        Interval(start + timedelta(minutes=10), start + timedelta(minutes=40), "light"),
    ]
    timeline = paint_binary_from_wearable_intervals(intervals)
    assert len(timeline) == 80  # 40 minutes
    assert timeline.epochs[0].label == BinaryLabel.AWAKE.value
    assert timeline.epochs[20].label == BinaryLabel.SLEEP.value


def test_collapse_phone_timeline():
    start = datetime(2026, 7, 12, 1, 0, tzinfo=timezone.utc)
    timeline = EpochTimeline(
        epochs=[
            Epoch(start, PhoneStage.AWAKE.value),
            Epoch(start + timedelta(seconds=30), PhoneStage.RESTLESS.value),
            Epoch(start + timedelta(seconds=60), PhoneStage.QUIET_SLEEP.value),
        ]
    )
    binary = collapse_phone_timeline(timeline)
    assert binary.labels() == [
        BinaryLabel.AWAKE.value,
        BinaryLabel.SLEEP.value,
        BinaryLabel.SLEEP.value,
    ]

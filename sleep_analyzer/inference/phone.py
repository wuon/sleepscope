from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from sleep_analyzer.inference.csv_parser import Recording, SensorSample
from sleep_analyzer.timeline import (
    EPOCH_SECONDS,
    Epoch,
    EpochTimeline,
    PhoneStage,
    ensure_aware,
    floor_to_epoch,
)

# Webster / Cole-Kripke style neighborhood weights on activity bins.
# D = scale * sum(w[k] * A[i+k]) for k in -4..+2
WEBSTER_WEIGHTS: dict[int, float] = {
    -4: 0.04,
    -3: 0.04,
    -2: 0.20,
    -1: 0.20,
    0: 2.00,
    1: 0.20,
    2: 0.04,
}
WEBSTER_SCALE = 0.125

# Audio spike: dB above rolling median baseline.
AUDIO_BASELINE_WINDOW = 5  # bins (~2.5 min)
AUDIO_SPIKE_THRESHOLD_DB = 8.0

# Movement band thresholds as overnight percentiles of Webster scores.
HIGH_MOVEMENT_PCT = 80.0
MODERATE_MOVEMENT_PCT = 40.0
SLIGHT_MOVEMENT_PCT = 20.0


@dataclass(frozen=True)
class PhoneBin:
    start: datetime
    activity: float
    webster_score: float
    db_median: float | None
    audio_spike: bool
    stage: PhoneStage


def infer_phone_timeline(recording: Recording) -> tuple[EpochTimeline, list[PhoneBin]]:
    """Build 30s Awake/Restless/QuietSleep timeline from sensor CSV recording."""
    if not recording.samples:
        raise ValueError("recording has no samples")

    samples = sorted(recording.samples, key=lambda s: s.timestamp)
    gravity = _percentile([s.accel_mag for s in samples], 50.0)
    bins = _bin_samples(samples, gravity)
    if not bins:
        raise ValueError("no 30-second bins could be formed from samples")

    activities = [item["activity"] for item in bins]
    webster_scores = _webster_scores(activities)
    db_series = [item["db_median"] for item in bins]
    spikes = _audio_spikes(db_series)

    high_cut = _percentile(webster_scores, HIGH_MOVEMENT_PCT)
    moderate_cut = _percentile(webster_scores, MODERATE_MOVEMENT_PCT)
    slight_cut = _percentile(webster_scores, SLIGHT_MOVEMENT_PCT)

    phone_bins: list[PhoneBin] = []
    epochs: list[Epoch] = []
    for index, raw in enumerate(bins):
        score = webster_scores[index]
        spike = spikes[index]
        slight = score >= slight_cut
        if score >= high_cut:
            stage = PhoneStage.AWAKE
        elif score >= moderate_cut:
            stage = PhoneStage.RESTLESS
        elif spike and slight:
            stage = PhoneStage.RESTLESS
        else:
            stage = PhoneStage.QUIET_SLEEP

        phone_bins.append(
            PhoneBin(
                start=raw["start"],
                activity=raw["activity"],
                webster_score=score,
                db_median=raw["db_median"],
                audio_spike=spike,
                stage=stage,
            )
        )
        epochs.append(Epoch(start=raw["start"], label=stage.value))

    timeline = EpochTimeline(epochs=epochs, provider="sleepscope")
    return timeline, phone_bins


def _bin_samples(
    samples: Sequence[SensorSample], gravity: float
) -> list[dict]:
    start = floor_to_epoch(samples[0].timestamp)
    end = ensure_aware(samples[-1].timestamp)
    last_bin_start = floor_to_epoch(end)
    bins: list[dict] = []
    sample_index = 0
    n = len(samples)
    cursor = start
    while cursor <= last_bin_start:
        bin_end = cursor + timedelta(seconds=EPOCH_SECONDS)
        bucket: list[SensorSample] = []
        while sample_index < n and ensure_aware(samples[sample_index].timestamp) < bin_end:
            if ensure_aware(samples[sample_index].timestamp) >= cursor:
                bucket.append(samples[sample_index])
            sample_index += 1
        if bucket:
            activities = [_activity(sample, gravity) for sample in bucket]
            valid_dbs = [sample.db for sample in bucket if sample.db is not None]
            bins.append(
                {
                    "start": cursor,
                    "activity": statistics.fmean(activities),
                    "db_median": statistics.median(valid_dbs) if valid_dbs else None,
                }
            )
        cursor = bin_end
    return bins


def _activity(sample: SensorSample, gravity: float) -> float:
    return abs(sample.accel_mag - gravity) + 2.0 * sample.gyro_mag


def _webster_scores(activities: Sequence[float]) -> list[float]:
    n = len(activities)
    scores: list[float] = []
    for index in range(n):
        total = 0.0
        for offset, weight in WEBSTER_WEIGHTS.items():
            neighbor = index + offset
            if 0 <= neighbor < n:
                total += weight * activities[neighbor]
            else:
                # Edge: repeat nearest edge activity.
                edge = activities[0] if neighbor < 0 else activities[-1]
                total += weight * edge
        scores.append(WEBSTER_SCALE * total)
    return scores


def _audio_spikes(db_medians: Sequence[float | None]) -> list[bool]:
    spikes: list[bool] = []
    half = AUDIO_BASELINE_WINDOW // 2
    for index, value in enumerate(db_medians):
        window_vals: list[float] = []
        for j in range(max(0, index - half), min(len(db_medians), index + half + 1)):
            candidate = db_medians[j]
            if candidate is not None:
                window_vals.append(candidate)
        if value is None or len(window_vals) < 2:
            spikes.append(False)
            continue
        baseline = statistics.median(window_vals)
        spikes.append(value >= baseline + AUDIO_SPIKE_THRESHOLD_DB)
    return spikes


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight

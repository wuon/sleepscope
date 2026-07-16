from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from sleep_analyzer.inference.csv_parser import Recording, SensorSample
from sleep_analyzer.metrics import EPOCH_MINUTES


@dataclass
class EpochFeatures:
    start: datetime
    end: datetime
    sample_count: int
    accel_mag_mean: float
    accel_mag_std: float
    accel_mag_max: float
    accel_mag_p95: float
    gyro_mag_mean: float
    gyro_mag_std: float
    gyro_mag_max: float
    motion_score: float
    db_mean: float | None
    db_std: float | None
    db_max: float | None
    db_valid_count: int
    peak_count: int
    rhythmic_score: float
    irregular_sound: bool
    manual_events: tuple[str, ...] = ()
    events: set[str] = field(default_factory=set)


def extract_epoch_features(
    recording: Recording,
    *,
    epoch_minutes: float = EPOCH_MINUTES,
) -> list[EpochFeatures]:
    """Bucket samples into fixed-length epochs and compute motion/sound features."""
    if not recording.samples:
        raise ValueError("recording has no samples")

    samples = sorted(recording.samples, key=lambda s: s.timestamp)
    session_start = samples[0].timestamp
    session_end = samples[-1].timestamp
    epoch_delta = timedelta(minutes=epoch_minutes)

    # Overnight baselines for relative thresholds.
    # Accel magnitude includes gravity (~1g); activity is deviation from that floor.
    accel_mags = [s.accel_mag for s in samples]
    gravity_baseline = _percentile(accel_mags, 50.0)
    motion_scores = [_activity(s, gravity_baseline) for s in samples]
    valid_dbs = [s.db for s in samples if s.db is not None]

    still_cut = _percentile(motion_scores, 40.0)
    micro_cut = _percentile(motion_scores, 60.0)
    toss_cut = _percentile(motion_scores, 90.0)
    active_cut = _percentile(motion_scores, 97.0)
    db_quiet_cut = _percentile(valid_dbs, 30.0) if valid_dbs else None
    db_elevated_cut = _percentile(valid_dbs, 70.0) if valid_dbs else None
    db_speech_cut = _percentile(valid_dbs, 90.0) if valid_dbs else None

    epochs: list[EpochFeatures] = []
    epoch_start = session_start
    sample_index = 0
    n = len(samples)

    while epoch_start <= session_end:
        epoch_end = epoch_start + epoch_delta
        bucket: list[SensorSample] = []
        while sample_index < n and samples[sample_index].timestamp < epoch_end:
            if samples[sample_index].timestamp >= epoch_start:
                bucket.append(samples[sample_index])
            sample_index += 1

        if bucket:
            epochs.append(
                _build_epoch(
                    bucket,
                    epoch_start=epoch_start,
                    epoch_end=epoch_end,
                    gravity_baseline=gravity_baseline,
                    still_cut=still_cut,
                    micro_cut=micro_cut,
                    toss_cut=toss_cut,
                    active_cut=active_cut,
                    db_quiet_cut=db_quiet_cut,
                    db_elevated_cut=db_elevated_cut,
                    db_speech_cut=db_speech_cut,
                )
            )
        epoch_start = epoch_end

    _annotate_bed_exit_return(epochs)
    return epochs


def _build_epoch(
    bucket: Sequence[SensorSample],
    *,
    epoch_start: datetime,
    epoch_end: datetime,
    gravity_baseline: float,
    still_cut: float,
    micro_cut: float,
    toss_cut: float,
    active_cut: float,
    db_quiet_cut: float | None,
    db_elevated_cut: float | None,
    db_speech_cut: float | None,
) -> EpochFeatures:
    accel_mags = [s.accel_mag for s in bucket]
    gyro_mags = [s.gyro_mag for s in bucket]
    motion_scores = [_activity(s, gravity_baseline) for s in bucket]
    valid_dbs = [s.db for s in bucket if s.db is not None]
    manual_events = tuple(s.event for s in bucket if s.event)

    accel_mean = statistics.fmean(accel_mags)
    accel_std = statistics.pstdev(accel_mags) if len(accel_mags) > 1 else 0.0
    accel_max = max(accel_mags)
    accel_p95 = _percentile(accel_mags, 95.0)
    gyro_mean = statistics.fmean(gyro_mags)
    gyro_std = statistics.pstdev(gyro_mags) if len(gyro_mags) > 1 else 0.0
    gyro_max = max(gyro_mags)
    motion_mean = statistics.fmean(motion_scores)
    motion_max = max(motion_scores)

    peak_threshold = max(micro_cut, still_cut * 1.5 if still_cut > 0 else micro_cut)
    micro_peaks = sum(1 for score in motion_scores if peak_threshold <= score < toss_cut)
    toss_peaks = sum(1 for score in motion_scores if score >= toss_cut)
    peak_count = micro_peaks + toss_peaks

    db_mean = statistics.fmean(valid_dbs) if valid_dbs else None
    db_std = statistics.pstdev(valid_dbs) if len(valid_dbs) > 1 else (0.0 if valid_dbs else None)
    db_max = max(valid_dbs) if valid_dbs else None
    rhythmic_score = _rhythmic_score(valid_dbs)
    sound_above_floor = db_quiet_cut is None or (
        db_mean is not None and db_mean >= db_quiet_cut
    )
    irregular_sound = bool(
        db_mean is not None
        and db_std is not None
        and db_std >= 2.0
        and rhythmic_score < 0.35
        and sound_above_floor
    )

    events: set[str] = set()
    if motion_mean <= still_cut and motion_max < toss_cut:
        events.add("still")
    elif micro_peaks >= 1 and motion_mean < active_cut:
        events.add("micro_move")
    if toss_peaks >= 1 or motion_max >= toss_cut:
        events.add("toss_turn")
    # Sustained high activity only — sparse toss/turn peaks are not wake by themselves.
    if motion_mean >= active_cut or (
        motion_mean >= micro_cut and toss_peaks >= max(4, len(bucket) // 15)
    ):
        events.add("active")

    if db_mean is not None and db_quiet_cut is not None and db_std is not None:
        if db_mean <= db_quiet_cut and db_std <= 3.0:
            events.add("quiet")
        if db_max is not None and db_elevated_cut is not None:
            if db_max >= db_speech_cut and (db_mean < db_elevated_cut or irregular_sound):
                # Short loud transient relative to epoch mean.
                if db_max - db_mean >= 8.0:
                    events.add("noise_spike")
        if db_elevated_cut is not None and db_mean >= db_elevated_cut:
            events.add("elevated_sound")
        if rhythmic_score >= 0.35 and db_elevated_cut is not None and db_mean >= db_quiet_cut:
            events.add("rhythmic_sound")
        if (
            db_speech_cut is not None
            and db_mean >= db_speech_cut
            and irregular_sound
            and "rhythmic_sound" not in events
        ):
            events.add("speech_like")

    if _is_manual_wake(manual_events):
        events.add("manual_wake")

    return EpochFeatures(
        start=epoch_start,
        end=epoch_end,
        sample_count=len(bucket),
        accel_mag_mean=accel_mean,
        accel_mag_std=accel_std,
        accel_mag_max=accel_max,
        accel_mag_p95=accel_p95,
        gyro_mag_mean=gyro_mean,
        gyro_mag_std=gyro_std,
        gyro_mag_max=gyro_max,
        motion_score=motion_mean,
        db_mean=db_mean,
        db_std=db_std,
        db_max=db_max,
        db_valid_count=len(valid_dbs),
        peak_count=peak_count,
        rhythmic_score=rhythmic_score,
        irregular_sound=irregular_sound,
        manual_events=manual_events,
        events=events,
    )


def _annotate_bed_exit_return(epochs: list[EpochFeatures]) -> None:
    """Mark bed exit/return using large motion followed by near-flat epochs."""
    if len(epochs) < 2:
        return

    motion_values = [e.motion_score for e in epochs]
    flat_cut = _percentile(motion_values, 15.0)
    exit_motion_cut = _percentile(motion_values, 85.0)

    for index, epoch in enumerate(epochs):
        if "toss_turn" not in epoch.events and "active" not in epoch.events:
            continue
        if epoch.motion_score < exit_motion_cut:
            continue
        # Look ahead for 1–2 unusually flat epochs.
        following = epochs[index + 1 : index + 3]
        if following and all(e.motion_score <= flat_cut for e in following):
            for flat_epoch in following:
                flat_epoch.events.add("bed_exit")

    in_exit = False
    for epoch in epochs:
        if "bed_exit" in epoch.events:
            in_exit = True
            continue
        if in_exit and (
            "active" in epoch.events
            or "toss_turn" in epoch.events
            or "micro_move" in epoch.events
        ):
            epoch.events.add("bed_return")
            in_exit = False


def _activity(sample: SensorSample, gravity_baseline: float) -> float:
    """Gravity-normalized activity: | |a| - g_floor | + weighted gyro magnitude."""
    return abs(sample.accel_mag - gravity_baseline) + 2.0 * sample.gyro_mag


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


def _rhythmic_score(dbs: Sequence[float]) -> float:
    """Rough periodicity score for snore-like dB envelopes (~2–8 s at ~1 Hz)."""
    if len(dbs) < 12:
        return 0.0
    series = list(dbs)
    mean = statistics.fmean(series)
    centered = [value - mean for value in series]
    variance = sum(v * v for v in centered) / len(centered)
    if variance <= 1e-9:
        return 0.0

    best = 0.0
    # Lags ~2–8 samples ≈ 2–8 seconds at 1 Hz.
    for lag in range(2, min(9, len(centered) // 2)):
        num = sum(
            centered[index] * centered[index + lag]
            for index in range(len(centered) - lag)
        )
        denom = (len(centered) - lag) * variance
        corr = num / denom if denom else 0.0
        best = max(best, corr)
    return max(0.0, best)


_MANUAL_WAKE_TOKENS = (
    "awake_in_bed",
    "out_of_bed",
    "awake",
    "wake",
    "wakeup",
    "wake_up",
    "bathroom",
    "alarm",
)


def _is_manual_wake(events: Sequence[str]) -> bool:
    for event in events:
        normalized = event.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in _MANUAL_WAKE_TOKENS:
            return True
        if "wake" in normalized or "awake" in normalized:
            return True
    return False

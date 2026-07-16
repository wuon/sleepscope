from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sleep_analyzer.inference.features import EpochFeatures
from sleep_analyzer.metrics import EPOCH_MINUTES


# Canonical SleepScope export labels.
STAGE_AWAKE = "Awake"
STAGE_LIGHT = "Light"
STAGE_DEEP = "Deep"
STAGE_REM = "REM"

DEEP_STILL_STREAK = 3  # epochs (~6 min)
SLEEP_ONSET_STILL_STREAK = 5  # epochs (~10 min)
REM_START_MINUTES = 90.0
REM_SHARE_CAP = 0.22
FINAL_WAKE_LOOKBACK = 3


@dataclass(frozen=True)
class StageEpoch:
    timestamp: datetime
    state: str
    events: tuple[str, ...]


def classify_epochs(epochs: Sequence[EpochFeatures]) -> list[StageEpoch]:
    """Map epoch features/events to wake / light / deep / rem with v1 rules."""
    if not epochs:
        raise ValueError("no epochs to classify")

    sleep_onset_index = _find_sleep_onset_index(epochs)
    final_wake_index = _find_final_awakening_index(epochs, sleep_onset_index)
    still_streak = _still_quiet_streaks(epochs)

    raw_stages: list[str] = []
    for index, epoch in enumerate(epochs):
        events = epoch.events
        minutes_since_onset = (
            (index - sleep_onset_index) * EPOCH_MINUTES
            if sleep_onset_index is not None and index >= sleep_onset_index
            else None
        )
        early_night = (
            minutes_since_onset is not None and minutes_since_onset < REM_START_MINUTES
        )
        late_night = (
            minutes_since_onset is not None and minutes_since_onset >= REM_START_MINUTES
        )
        before_onset = sleep_onset_index is not None and index < sleep_onset_index
        after_final = final_wake_index is not None and index >= final_wake_index

        if (
            "manual_wake" in events
            or "bed_exit" in events
            or "active" in events
            or "speech_like" in events
            or before_onset
            or after_final
        ):
            raw_stages.append(STAGE_AWAKE)
            continue

        still_quiet = still_streak[index] >= DEEP_STILL_STREAK
        recent_toss = _recent_toss_turn(epochs, index, lookback=2)

        if still_quiet and not recent_toss and early_night:
            raw_stages.append(STAGE_DEEP)
            continue

        mostly_quiet_motion = (
            ("still" in events or "micro_move" in events)
            and "active" not in events
            and "bed_exit" not in events
        )

        if (
            late_night
            and mostly_quiet_motion
            and not recent_toss
            and not still_quiet
            and (
                "micro_move" in events
                or epoch.irregular_sound
                or "elevated_sound" in events
            )
        ):
            raw_stages.append(STAGE_REM)
            continue

        if still_quiet and not recent_toss and late_night and not epoch.irregular_sound:
            # Prolonged quiet stillness late night without twitch/irregular sound → deep.
            raw_stages.append(STAGE_DEEP)
            continue

        # Late-night residual low motion with twitches → REM even inside a still bout.
        if (
            late_night
            and mostly_quiet_motion
            and not recent_toss
            and ("micro_move" in events or epoch.irregular_sound)
        ):
            raw_stages.append(STAGE_REM)
            continue

        raw_stages.append(STAGE_LIGHT)

    smoothed = _smooth_stages(raw_stages)
    capped = _cap_rem_share(smoothed)
    bridged = _bridge_deep_wake(capped)

    # Session-level event annotations for debugging / emit metadata consumers.
    result: list[StageEpoch] = []
    for index, epoch in enumerate(epochs):
        annotated = set(epoch.events)
        if sleep_onset_index is not None and index == sleep_onset_index:
            annotated.add("sleep_onset")
        if final_wake_index is not None and index == final_wake_index:
            annotated.add("final_awakening")
        if sleep_onset_index is not None and index >= sleep_onset_index:
            annotated.add("cycle_phase")
        result.append(
            StageEpoch(
                timestamp=epoch.start,
                state=bridged[index],
                events=tuple(sorted(annotated)),
            )
        )
    return result


def _find_sleep_onset_index(epochs: Sequence[EpochFeatures]) -> int | None:
    streak = 0
    for index, epoch in enumerate(epochs):
        quietish = "still" in epoch.events or (
            "active" not in epoch.events and "speech_like" not in epoch.events
        )
        if quietish and "manual_wake" not in epoch.events and "bed_exit" not in epoch.events:
            streak += 1
            if streak >= SLEEP_ONSET_STILL_STREAK:
                return index - SLEEP_ONSET_STILL_STREAK + 1
        else:
            streak = 0
    # Short recordings: onset at first non-active epoch.
    for index, epoch in enumerate(epochs):
        if "active" not in epoch.events and "manual_wake" not in epoch.events:
            return index
    return 0


def _find_final_awakening_index(
    epochs: Sequence[EpochFeatures], sleep_onset_index: int | None
) -> int | None:
    start = sleep_onset_index or 0
    last_active: int | None = None
    for index in range(len(epochs) - 1, start - 1, -1):
        events = epochs[index].events
        if "active" in events or "manual_wake" in events or "speech_like" in events:
            last_active = index
            break
    if last_active is None:
        return None
    # Require the active bout to sit near the end of the recording.
    if last_active < len(epochs) - FINAL_WAKE_LOOKBACK:
        return None
    return last_active


def _still_quiet_streaks(epochs: Sequence[EpochFeatures]) -> list[int]:
    """Bout length for quiet, low-motion epochs (deep candidates)."""
    flags = [_is_still_quiet(epoch) for epoch in epochs]
    result = [0] * len(epochs)
    index = 0
    while index < len(epochs):
        if not flags[index]:
            index += 1
            continue
        end = index
        while end + 1 < len(epochs) and flags[end + 1]:
            end += 1
        length = end - index + 1
        for pos in range(index, end + 1):
            result[pos] = length
        index = end + 1
    return result


def _is_still_quiet(epoch: EpochFeatures) -> bool:
    if "active" in epoch.events or "toss_turn" in epoch.events:
        return False
    if "speech_like" in epoch.events or "manual_wake" in epoch.events:
        return False
    if "bed_exit" in epoch.events:
        return False
    quiet_ok = (
        "quiet" in epoch.events
        or epoch.db_mean is None
        or "elevated_sound" not in epoch.events
    )
    still_ok = "still" in epoch.events or (
        "micro_move" not in epoch.events and "active" not in epoch.events
    )
    return quiet_ok and still_ok


def _recent_toss_turn(
    epochs: Sequence[EpochFeatures], index: int, *, lookback: int
) -> bool:
    start = max(0, index - lookback)
    return any("toss_turn" in epochs[pos].events for pos in range(start, index + 1))


def _smooth_stages(stages: Sequence[str]) -> list[str]:
    """3-epoch majority filter."""
    if len(stages) < 3:
        return list(stages)
    result = list(stages)
    for index in range(1, len(stages) - 1):
        window = (stages[index - 1], stages[index], stages[index + 1])
        result[index] = _majority(window)
    return result


def _majority(window: tuple[str, str, str]) -> str:
    counts: dict[str, int] = {}
    for stage in window:
        counts[stage] = counts.get(stage, 0) + 1
    # Prefer center on ties.
    best = window[1]
    best_count = counts[best]
    for stage, count in counts.items():
        if count > best_count:
            best = stage
            best_count = count
    return best


def _cap_rem_share(stages: Sequence[str]) -> list[str]:
    asleep_indices = [
        index
        for index, stage in enumerate(stages)
        if stage in (STAGE_LIGHT, STAGE_DEEP, STAGE_REM)
    ]
    if not asleep_indices:
        return list(stages)

    rem_indices = [index for index, stage in enumerate(stages) if stage == STAGE_REM]
    max_rem = max(1, int(len(asleep_indices) * REM_SHARE_CAP))
    if len(rem_indices) <= max_rem:
        return list(stages)

    # Keep later REM epochs (more physiologically plausible), demote earliest extras to light.
    keep = set(rem_indices[-max_rem:])
    result = list(stages)
    for index in rem_indices:
        if index not in keep:
            result[index] = STAGE_LIGHT
    return result


def _bridge_deep_wake(stages: Sequence[str]) -> list[str]:
    """Forbid direct deep↔wake transitions without a light bridge."""
    result = list(stages)
    for index in range(1, len(result)):
        prev, curr = result[index - 1], result[index]
        if prev == STAGE_DEEP and curr == STAGE_AWAKE:
            result[index] = STAGE_LIGHT
        elif prev == STAGE_AWAKE and curr == STAGE_DEEP:
            result[index] = STAGE_LIGHT
    return result

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sleep_analyzer.inference.emit import infer_sleepscope_epochs
from sleep_analyzer.loaders.base import register_loader
from sleep_analyzer.metrics import EPOCH_MINUTES, build_session_metrics
from sleep_analyzer.models import SessionMetrics

SLEEPSCOPE_STATE_MAP = {
    "deep": "deep",
    "light": "light",
    "rem": "rem",
    "awake": "awake",
}


class SleepScopeLoader:
    """Load SleepScope phone-sensor CSV, infer stages, normalize to SessionMetrics."""

    name = "sleepscope"

    def load(self, path: Path) -> SessionMetrics:
        path = Path(path)
        if path.suffix.lower() != ".csv":
            raise ValueError(
                f"{path}: SleepScope reference must be a sensor CSV "
                f"(accel / gyro / dB / Event). Got '{path.suffix or '(no extension)'}'."
            )

        payload = infer_sleepscope_epochs(path)
        return self._metrics_from_epochs(payload, path)

    def _metrics_from_epochs(self, payload: list, path: Path) -> SessionMetrics:
        stage_minutes = {"deep": 0.0, "light": 0.0, "rem": 0.0, "awake": 0.0}
        timestamps: list[datetime] = []

        for index, row in enumerate(payload):
            if not isinstance(row, dict):
                raise ValueError(f"{path}: epoch {index} must be an object")
            if "timestamp" not in row or "state" not in row:
                raise ValueError(
                    f"{path}: epoch {index} requires 'timestamp' and 'state' fields"
                )

            state_key = str(row["state"]).strip().lower()
            if state_key not in SLEEPSCOPE_STATE_MAP:
                raise ValueError(
                    f"{path}: epoch {index} has unsupported state '{row['state']}'. "
                    "Expected one of: Deep, Light, REM, Awake."
                )

            stage_minutes[SLEEPSCOPE_STATE_MAP[state_key]] += EPOCH_MINUTES
            timestamps.append(_parse_timestamp(row["timestamp"], path, index))

        start = min(timestamps)
        end = max(timestamps) + timedelta(minutes=EPOCH_MINUTES)
        duration = len(payload) * EPOCH_MINUTES

        return build_session_metrics(
            provider=self.name,
            start=start,
            end=end,
            deep_min=stage_minutes["deep"],
            light_min=stage_minutes["light"],
            rem_min=stage_minutes["rem"],
            awake_min=stage_minutes["awake"],
            duration_min=duration,
        )


def _parse_timestamp(value: object, path: Path, index: int) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{path}: epoch {index} timestamp must be an ISO-8601 string")
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{path}: epoch {index} has invalid timestamp '{value}'") from exc


register_loader(SleepScopeLoader())

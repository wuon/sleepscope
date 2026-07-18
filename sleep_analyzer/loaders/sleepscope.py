from __future__ import annotations

from pathlib import Path

from sleep_analyzer.inference.emit import infer_phone_stages_from_csv
from sleep_analyzer.loaders.base import register_loader
from sleep_analyzer.metrics import build_binary_session
from sleep_analyzer.models import BinarySession


class SleepScopeLoader:
    """Load SleepScope sensor CSV → 30s phone stages → binary Sleep/Awake timeline."""

    name = "sleepscope"

    def load(self, path: Path) -> BinarySession:
        path = Path(path)
        if path.suffix.lower() != ".csv":
            raise ValueError(
                f"{path}: SleepScope reference must be a sensor CSV "
                f"(accel / gyro / dB / Event). Got '{path.suffix or '(no extension)'}'."
            )

        phone_timeline = infer_phone_stages_from_csv(path)
        return build_binary_session(
            provider=self.name,
            timeline=phone_timeline,
            binary=False,
        )


register_loader(SleepScopeLoader())

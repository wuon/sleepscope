from __future__ import annotations

from pathlib import Path

import pytest

from sleep_analyzer.loaders.sleepscope import SleepScopeLoader

FIXTURES = Path(__file__).parent / "fixtures"


def test_sleepscope_loader_infers_from_csv():
    metrics = SleepScopeLoader().load(FIXTURES / "sensor_sample.csv")
    assert metrics.provider == "sleepscope"
    assert metrics.duration_min == 2.0
    assert metrics.awake_min == 2.0
    assert metrics.asleep_min == 0.0
    assert metrics.efficiency == pytest.approx(0.0)


def test_sleepscope_rejects_non_csv(tmp_path: Path):
    path = tmp_path / "epochs.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="sensor CSV"):
        SleepScopeLoader().load(path)

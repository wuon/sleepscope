from __future__ import annotations

from pathlib import Path

import pytest

from sleep_analyzer.loaders.sleepscope import SleepScopeLoader

FIXTURES = Path(__file__).parent / "fixtures"


def test_sleepscope_loader_from_csv():
    session = SleepScopeLoader().load(FIXTURES / "sensor_sample.csv")
    assert session.provider == "sleepscope"
    assert session.duration_min > 0
    assert session.asleep_min + session.awake_min == pytest.approx(session.duration_min)
    assert all(e.label in {"Sleep", "Awake"} for e in session.timeline.epochs)


def test_sleepscope_rejects_non_csv(tmp_path: Path):
    path = tmp_path / "epochs.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="sensor CSV"):
        SleepScopeLoader().load(path)

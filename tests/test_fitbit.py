from __future__ import annotations

from pathlib import Path

import pytest

from sleep_analyzer.loaders.fitbit import FitbitLoader

FIXTURES = Path(__file__).parent / "fixtures"


def test_fitbit_loader_levels_data_binary():
    session = FitbitLoader().load(FIXTURES / "fitbit_sample.json")
    assert session.provider == "fitbit"
    assert session.duration_min == pytest.approx(60.0)
    assert session.asleep_min == pytest.approx(45.0)
    assert session.awake_min == pytest.approx(15.0)
    assert all(e.label in {"Sleep", "Awake"} for e in session.timeline.epochs)

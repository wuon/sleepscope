from __future__ import annotations

from pathlib import Path

import pytest

from sleep_analyzer.loaders.apple_watch import AppleWatchLoader
from sleep_analyzer.timeline import BinaryLabel

FIXTURES = Path(__file__).parent / "fixtures"


def test_apple_watch_loader_stages_binary():
    session = AppleWatchLoader().load(FIXTURES / "apple_watch_sample.xml")
    assert session.provider == "apple_watch"
    # InBed wrapper is ignored when stage samples exist: 01:00–02:00 = 60 min.
    assert session.duration_min == pytest.approx(60.0)
    # Awake 10+5 min, Sleep Core20+Deep15+REM10 = 45 min.
    assert session.asleep_min == pytest.approx(45.0)
    assert session.awake_min == pytest.approx(15.0)
    assert all(e.label in {"Sleep", "Awake"} for e in session.timeline.epochs)
    assert session.timeline.epochs[0].label == BinaryLabel.AWAKE.value
    assert session.timeline.epochs[20].label == BinaryLabel.SLEEP.value

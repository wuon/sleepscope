from __future__ import annotations

from pathlib import Path

import pytest

from sleep_analyzer.loaders.oura import OuraLoader
from sleep_analyzer.timeline import BinaryLabel

FIXTURES = Path(__file__).parent / "fixtures"


def test_oura_loader_phases_binary():
    session = OuraLoader().load(FIXTURES / "oura_sample.json", day="2026-07-19")
    assert session.provider == "oura"
    # Short 01:14–01:17 + gap + long 02:00–02:10 on the 30s grid.
    assert session.duration_min == pytest.approx(57.0)
    assert all(e.label in {"Sleep", "Awake"} for e in session.timeline.epochs)
    assert session.asleep_min > 0
    assert session.awake_min > 0
    assert any(e.label == BinaryLabel.SLEEP.value for e in session.timeline.epochs)


def test_oura_loader_requires_day_for_multi_day(tmp_path: Path):
    path = tmp_path / "multi.json"
    path.write_text(
        """
        {
          "data": [
            {
              "day": "2026-07-19",
              "bedtime_start": "2026-07-19T02:00:00.000-07:00",
              "sleep_phase_30_sec": "2222"
            },
            {
              "day": "2026-07-20",
              "bedtime_start": "2026-07-20T02:00:00.000-07:00",
              "sleep_phase_30_sec": "2222"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="multiple days"):
        OuraLoader().load(path)

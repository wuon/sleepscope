from __future__ import annotations

import json
from pathlib import Path

import pytest

from sleep_analyzer.loaders.fitbit import FitbitLoader

FIXTURES = Path(__file__).parent / "fixtures"


def test_fitbit_loader_prefers_summary():
    metrics = FitbitLoader().load(FIXTURES / "fitbit_sample.json")
    assert metrics.provider == "fitbit"
    assert metrics.duration_min == 16.0
    assert metrics.deep_min == 4.0
    assert metrics.light_min == 6.0
    assert metrics.rem_min == 2.0
    assert metrics.awake_min == 4.0
    assert metrics.asleep_min == 12.0
    assert metrics.efficiency == pytest.approx(0.75)


def test_fitbit_loader_takeout_mainsleep(tmp_path: Path):
    payload = [
        {
            "logId": 1,
            "dateOfSleep": "2026-07-11",
            "startTime": "2026-07-11T01:00:00.000",
            "endTime": "2026-07-11T02:00:00.000",
            "timeInBed": 60,
            "mainSleep": True,
            "type": "stages",
            "levels": {
                "summary": {
                    "deep": {"minutes": 10},
                    "light": {"minutes": 30},
                    "rem": {"minutes": 10},
                    "wake": {"minutes": 10},
                }
            },
        },
        {
            "logId": 2,
            "dateOfSleep": "2026-07-12",
            "startTime": "2026-07-12T01:00:00.000",
            "endTime": "2026-07-12T02:40:00.000",
            "timeInBed": 100,
            "mainSleep": True,
            "type": "stages",
            "levels": {
                "summary": {
                    "deep": {"minutes": 20},
                    "light": {"minutes": 50},
                    "rem": {"minutes": 20},
                    "wake": {"minutes": 10},
                }
            },
        },
    ]
    path = tmp_path / "takeout.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    metrics = FitbitLoader().load(path)
    assert metrics.deep_min == 20.0
    assert metrics.duration_min == 100.0

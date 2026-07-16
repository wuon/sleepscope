from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sleep_analyzer.compare import compare_many
from sleep_analyzer.inference.classify import (
    STAGE_AWAKE,
    STAGE_DEEP,
    STAGE_LIGHT,
    STAGE_REM,
    classify_epochs,
)
from sleep_analyzer.inference.csv_parser import parse_sensor_csv
from sleep_analyzer.inference.emit import infer_and_write, infer_sleepscope_epochs
from sleep_analyzer.inference.features import extract_epoch_features
from sleep_analyzer.loaders.sleepscope import SleepScopeLoader

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_sensor_csv_metadata_and_invalid_db():
    recording = parse_sensor_csv(FIXTURES / "sensor_sample.csv")
    assert recording.participant == "ALEX"
    assert recording.note == "test"
    assert recording.started is not None
    assert recording.started.year == 2026
    assert len(recording.samples) >= 30

    # Sentinel floors become None.
    assert recording.samples[0].db is None
    assert recording.samples[-1].db is None

    # Manual events preserved.
    events = {s.event for s in recording.samples if s.event}
    assert "awake_in_bed" in events
    assert "test log wake up" in events


def test_short_recording_infers_awake_from_manual_events():
    epochs = infer_sleepscope_epochs(FIXTURES / "sensor_sample.csv")
    assert epochs
    assert all("timestamp" in row and "state" in row for row in epochs)
    assert any(row["state"] == STAGE_AWAKE for row in epochs)


def test_synthetic_night_produces_all_stages(tmp_path: Path):
    csv_path = tmp_path / "synthetic_night.csv"
    _write_synthetic_night(csv_path)

    recording = parse_sensor_csv(csv_path)
    features = extract_epoch_features(recording)
    assert len(features) >= 100  # ~3.5+ hours at 2-min epochs

    # Early still/quiet stretch should mark still events.
    still_epochs = [e for e in features if "still" in e.events]
    assert still_epochs

    stages = classify_epochs(features)
    labels = {epoch.state for epoch in stages}
    assert STAGE_AWAKE in labels
    assert STAGE_LIGHT in labels
    assert STAGE_DEEP in labels
    assert STAGE_REM in labels

    # REM share capped.
    rem_count = sum(1 for epoch in stages if epoch.state == STAGE_REM)
    asleep = sum(
        1 for epoch in stages if epoch.state in (STAGE_LIGHT, STAGE_DEEP, STAGE_REM)
    )
    assert rem_count / asleep <= 0.25


def test_infer_writes_sleepscope_json(tmp_path: Path):
    csv_path = tmp_path / "night.csv"
    out_path = tmp_path / "epochs.json"
    _write_synthetic_night(csv_path, hours=2.0)

    written = infer_and_write(csv_path, out_path)
    assert written.exists()

    epochs = json.loads(written.read_text(encoding="utf-8"))
    assert epochs
    assert all("timestamp" in row and "state" in row for row in epochs)

    # Compare path still uses the CSV, not the optional JSON dump.
    metrics = SleepScopeLoader().load(csv_path)
    assert metrics.provider == "sleepscope"
    assert metrics.duration_min == pytest.approx(len(epochs) * 2.0)
    assert metrics.asleep_min + metrics.awake_min == pytest.approx(metrics.duration_min)


def test_sleepscope_loader_accepts_csv(tmp_path: Path):
    csv_path = tmp_path / "night.csv"
    _write_synthetic_night(csv_path, hours=2.0)

    metrics = SleepScopeLoader().load(csv_path)
    assert metrics.provider == "sleepscope"
    assert metrics.duration_min == pytest.approx(
        len(infer_sleepscope_epochs(csv_path)) * 2.0
    )


def test_compare_pipeline_with_csv_reference(tmp_path: Path):
    csv_path = tmp_path / "sensor.csv"
    _write_synthetic_night(csv_path, hours=2.0)
    fitbit_src = FIXTURES / "fitbit_sample.json"
    fitbit_path = tmp_path / "fitbit.json"
    fitbit_path.write_text(fitbit_src.read_text(encoding="utf-8"), encoding="utf-8")

    manifest = tmp_path / "night.json"
    manifest.write_text(
        json.dumps(
            {
                "id": "csv-ref-night",
                "date": "2026-07-16",
                "reference": {"provider": "sleepscope", "path": "sensor.csv"},
                "comparisons": [{"provider": "fitbit", "path": "fitbit.json"}],
            }
        ),
        encoding="utf-8",
    )

    deltas = compare_many([manifest])
    assert len(deltas) == 1
    assert deltas[0].reference.provider == "sleepscope"
    assert deltas[0].comparison.provider == "fitbit"
    assert deltas[0].reference.duration_min > 0


def _write_synthetic_night(path: Path, *, hours: float = 4.0) -> None:
    """Generate a structured phone-on-bed night for classifier tests."""
    start = datetime(2026, 7, 16, 23, 0, 0, tzinfo=timezone.utc)
    total_seconds = int(hours * 3600)
    rows: list[dict[str, object]] = []

    for second in range(total_seconds):
        ts = start + timedelta(seconds=second)
        minute = second / 60.0

        # Phase schedule:
        # 0–20 min: awake / restless
        # 20–90 min: deep-like stillness
        # 90–150 min: light with micro-moves
        # 150–210 min: rem-like stillness + twitches
        # last 10 min: wake
        if minute < 20 or minute >= hours * 60 - 10:
            ax, ay, az = _restless_accel(second)
            gx, gy, gz = _restless_gyro(second)
            db = -40.0 + 8.0 * math.sin(second / 3.0)
            event = "awake_in_bed" if second % 120 == 0 and minute < 20 else ""
        elif minute < 90:
            ax, ay, az = _still_accel(second, noise=0.0005)
            gx, gy, gz = 0.0004, 0.0, -0.0004
            db = -55.0 + 0.2 * math.sin(second / 17.0)
            event = ""
        elif minute < 150:
            ax, ay, az = _still_accel(second, noise=0.01)
            if second % 45 == 0:
                ax, ay, az = 0.2, -0.7, -0.5
            gx, gy, gz = 0.02 * math.sin(second / 11.0), 0.01, -0.01
            db = -52.0 + 1.5 * math.sin(second / 9.0)
            event = ""
        else:
            ax, ay, az = _still_accel(second, noise=0.002)
            if second % 90 == 0:
                ax += 0.03
                gx, gy, gz = 0.04, -0.01, 0.01
            else:
                gx, gy, gz = 0.0005, 0.0, -0.0005
            # Irregular non-periodic sound bursts for REM heuristic.
            burst = 8.0 if (second % 17) in (0, 1, 5) else 0.0
            db = -54.0 + burst + 0.4 * math.sin(second * 1.7)
            event = ""

        rows.append(
            {
                "Timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "Accel_X": f"{ax:.4f}",
                "Accel_Y": f"{ay:.4f}",
                "Accel_Z": f"{az:.4f}",
                "Gyro_X": f"{gx:.4f}",
                "Gyro_Y": f"{gy:.4f}",
                "Gyro_Z": f"{gz:.4f}",
                "dB": f"{db:.1f}",
                "Event": event,
            }
        )

    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# participant=TEST,,,,,,,,\n")
        handle.write(f"# started={start.isoformat().replace('+00:00', 'Z')},,,,,,,,\n")
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Timestamp",
                "Accel_X",
                "Accel_Y",
                "Accel_Z",
                "Gyro_X",
                "Gyro_Y",
                "Gyro_Z",
                "dB",
                "Event",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
        handle.write("# note=synthetic,,,,,,,,\n")


def _still_accel(second: int, *, noise: float) -> tuple[float, float, float]:
    return (
        0.001 + noise * math.sin(second / 29.0),
        -0.80 + noise * math.cos(second / 31.0),
        -0.59 + noise * math.sin(second / 37.0),
    )


def _restless_accel(second: int) -> tuple[float, float, float]:
    return (
        0.3 * math.sin(second / 2.0),
        -0.5 + 0.4 * math.cos(second / 3.0),
        -0.4 + 0.5 * math.sin(second / 5.0),
    )


def _restless_gyro(second: int) -> tuple[float, float, float]:
    return (
        0.8 * math.sin(second / 2.5),
        0.6 * math.cos(second / 4.0),
        -0.5 * math.sin(second / 3.0),
    )

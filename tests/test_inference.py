from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sleep_analyzer.compare import compare_many
from sleep_analyzer.inference.emit import infer_and_write, infer_phone_stages_from_csv
from sleep_analyzer.inference.csv_parser import parse_sensor_csv
from sleep_analyzer.loaders.sleepscope import SleepScopeLoader
from sleep_analyzer.timeline import BinaryLabel, PhoneStage, collapse_phone_timeline, minutes_for_label

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_sensor_csv_metadata_and_invalid_db():
    recording = parse_sensor_csv(FIXTURES / "sensor_sample.csv")
    assert recording.participant == "ALEX"
    assert recording.samples[0].db is None


def test_parse_sensor_csv_z_timestamps_are_utc():
    recording = parse_sensor_csv(FIXTURES / "sensor_sample.csv")
    started = recording.started
    assert started is not None
    # Z suffix is real UTC (00:28 PDT), not Pacific wall clock.
    assert started == datetime(2026, 7, 16, 1, 28, 25, 293000, tzinfo=timezone.utc)
    assert recording.samples[0].timestamp.tzinfo == timezone.utc
    assert recording.samples[0].timestamp.hour == 1


def test_short_recording_infers_phone_stages():
    timeline = infer_phone_stages_from_csv(FIXTURES / "sensor_sample.csv")
    assert len(timeline) >= 1
    assert all(
        epoch.label
        in {
            PhoneStage.AWAKE.value,
            PhoneStage.RESTLESS.value,
            PhoneStage.QUIET_SLEEP.value,
        }
        for epoch in timeline.epochs
    )


def test_synthetic_night_binary_sleep_awake(tmp_path: Path):
    csv_path = tmp_path / "synthetic_night.csv"
    _write_synthetic_night(csv_path, hours=3.0)

    phone = infer_phone_stages_from_csv(csv_path)
    binary = collapse_phone_timeline(phone)
    asleep = minutes_for_label(binary, BinaryLabel.SLEEP.value)
    awake = minutes_for_label(binary, BinaryLabel.AWAKE.value)
    assert asleep > 0
    assert awake > 0
    assert asleep + awake == pytest.approx(len(binary) * 0.5)


def test_infer_writes_phone_stage_json(tmp_path: Path):
    csv_path = tmp_path / "night.csv"
    out_path = tmp_path / "epochs.json"
    _write_synthetic_night(csv_path, hours=1.5)

    written = infer_and_write(csv_path, out_path)
    epochs = json.loads(written.read_text(encoding="utf-8"))
    assert epochs

    session = SleepScopeLoader().load(csv_path)
    assert session.provider == "sleepscope"
    assert session.asleep_min + session.awake_min == pytest.approx(session.duration_min)


def test_compare_pipeline_with_fitbit(tmp_path: Path):
    csv_path = tmp_path / "sensor.csv"
    _write_synthetic_night(csv_path, hours=2.0)
    fitbit_path = tmp_path / "fitbit.json"
    fitbit_path.write_text(
        (FIXTURES / "fitbit_sample.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest = tmp_path / "night.json"
    manifest.write_text(
        json.dumps(
            {
                "id": "csv-fitbit",
                "reference": {"provider": "sleepscope", "path": "sensor.csv"},
                "comparisons": [{"provider": "fitbit", "path": "fitbit.json"}],
            }
        ),
        encoding="utf-8",
    )
    comparisons = compare_many([manifest])
    assert len(comparisons) == 1
    assert comparisons[0].comparison.provider == "fitbit"


def _write_synthetic_night(path: Path, *, hours: float = 3.0) -> None:
    start = datetime(2026, 7, 16, 23, 0, 0, tzinfo=timezone.utc)
    total_seconds = int(hours * 3600)
    rows: list[dict[str, object]] = []

    for second in range(total_seconds):
        ts = start + timedelta(seconds=second)
        minute = second / 60.0
        if minute < 15 or minute >= hours * 60 - 10:
            ax, ay, az = _restless_accel(second)
            gx, gy, gz = _restless_gyro(second)
            db = -40.0 + 10.0 * math.sin(second / 2.0)
            event = "awake_in_bed" if second % 180 == 0 and minute < 15 else ""
        elif minute < 90:
            ax, ay, az = _still_accel(second, noise=0.0005)
            gx, gy, gz = 0.0003, 0.0, -0.0003
            db = -55.0 + 0.2 * math.sin(second / 17.0)
            event = ""
        else:
            ax, ay, az = _still_accel(second, noise=0.008)
            gx, gy, gz = 0.02 * math.sin(second / 7.0), 0.01, 0.0
            burst = 10.0 if second % 20 < 2 else 0.0
            db = -52.0 + burst
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

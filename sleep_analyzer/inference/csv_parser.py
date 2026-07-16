from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# Mic floor / muted sentinels seen in prototype exports.
INVALID_DB_THRESHOLD = -100.0

REQUIRED_COLUMNS = (
    "Timestamp",
    "Accel_X",
    "Accel_Y",
    "Accel_Z",
    "Gyro_X",
    "Gyro_Y",
    "Gyro_Z",
    "dB",
    "Event",
)


@dataclass(frozen=True)
class SensorSample:
    timestamp: datetime
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    db: float | None
    event: str | None

    @property
    def accel_mag(self) -> float:
        return math.sqrt(
            self.accel_x * self.accel_x
            + self.accel_y * self.accel_y
            + self.accel_z * self.accel_z
        )

    @property
    def gyro_mag(self) -> float:
        return math.sqrt(
            self.gyro_x * self.gyro_x
            + self.gyro_y * self.gyro_y
            + self.gyro_z * self.gyro_z
        )


@dataclass(frozen=True)
class Recording:
    participant: str | None
    started: datetime | None
    note: str | None
    samples: tuple[SensorSample, ...]
    path: str | None = None


def parse_sensor_csv(path: Path | str) -> Recording:
    """Parse prototype phone-sensor CSV with `# key=value` metadata headers."""
    path = Path(path)
    with path.open(encoding="utf-8", newline="") as handle:
        metadata: dict[str, str] = {}
        header: list[str] | None = None
        data_lines: list[str] = []

        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if not line.strip():
                continue
            if line.startswith("#"):
                key, value = _parse_metadata_line(line)
                metadata[key] = value
                continue
            if header is None:
                header = next(csv.reader([line]))
                _validate_header(header, path)
                continue
            data_lines.append(line)

        if header is None:
            raise ValueError(f"{path}: missing CSV header row")

        reader = csv.DictReader(data_lines, fieldnames=header)
        samples: list[SensorSample] = []
        for index, row in enumerate(reader):
            samples.append(_parse_row(row, path, index))

    if not samples:
        raise ValueError(f"{path}: no sensor samples found")

    return Recording(
        participant=metadata.get("participant") or None,
        started=_parse_optional_timestamp(metadata.get("started"), path, field="started"),
        note=metadata.get("note") or None,
        samples=tuple(samples),
        path=str(path),
    )


def _parse_metadata_line(line: str) -> tuple[str, str]:
    body = line[1:].strip()
    # Trailing commas from spreadsheet exports: `# participant=ALEX,,,,,,,,`
    body = body.rstrip(",").strip()
    if "=" not in body:
        raise ValueError(f"Invalid metadata line (expected key=value): {line!r}")
    key, value = body.split("=", 1)
    return key.strip().lower(), value.strip()


def _validate_header(header: list[str], path: Path) -> None:
    normalized = [col.strip() for col in header]
    missing = [col for col in REQUIRED_COLUMNS if col not in normalized]
    if missing:
        raise ValueError(
            f"{path}: CSV header missing columns: {', '.join(missing)}. "
            f"Found: {', '.join(normalized)}"
        )


def _parse_row(row: dict[str, str | None], path: Path, index: int) -> SensorSample:
    try:
        timestamp = _parse_timestamp(row.get("Timestamp"), path, index)
        accel_x = _parse_float(row.get("Accel_X"), path, index, "Accel_X")
        accel_y = _parse_float(row.get("Accel_Y"), path, index, "Accel_Y")
        accel_z = _parse_float(row.get("Accel_Z"), path, index, "Accel_Z")
        gyro_x = _parse_float(row.get("Gyro_X"), path, index, "Gyro_X")
        gyro_y = _parse_float(row.get("Gyro_Y"), path, index, "Gyro_Y")
        gyro_z = _parse_float(row.get("Gyro_Z"), path, index, "Gyro_Z")
        db_raw = _parse_float(row.get("dB"), path, index, "dB")
    except ValueError as exc:
        raise ValueError(f"{path}: row {index}: {exc}") from exc

    event_raw = (row.get("Event") or "").strip()
    event = event_raw or None
    db = None if db_raw <= INVALID_DB_THRESHOLD else db_raw

    return SensorSample(
        timestamp=timestamp,
        accel_x=accel_x,
        accel_y=accel_y,
        accel_z=accel_z,
        gyro_x=gyro_x,
        gyro_y=gyro_y,
        gyro_z=gyro_z,
        db=db,
        event=event,
    )


def _parse_float(value: str | None, path: Path, index: int, field: str) -> float:
    if value is None or str(value).strip() == "":
        raise ValueError(f"{path}: row {index} missing {field}")
    try:
        return float(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{path}: row {index} invalid {field} '{value}'") from exc


def _parse_timestamp(value: str | None, path: Path, index: int) -> datetime:
    if value is None or not str(value).strip():
        raise ValueError(f"{path}: row {index} missing Timestamp")
    return _parse_iso(str(value).strip(), path, f"row {index} Timestamp")


def _parse_optional_timestamp(
    value: str | None, path: Path, *, field: str
) -> datetime | None:
    if value is None or not value.strip():
        return None
    return _parse_iso(value.strip(), path, field)


def _parse_iso(value: str, path: Path, field: str) -> datetime:
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{path}: {field} has invalid timestamp '{value}'") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed

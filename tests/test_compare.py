from __future__ import annotations

from pathlib import Path

from sleep_analyzer.compare import compare_many, discover_inputs, parse_night_manifest
from sleep_analyzer.report import (
    format_console_report,
    write_comparison_timelines,
    write_hypnogram_plots,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_and_compare_night_manifest():
    manifest = parse_night_manifest(FIXTURES / "night_manifest.json")
    assert manifest.reference.provider == "sleepscope"
    assert manifest.comparisons[0].provider == "fitbit"

    comparisons = compare_many([FIXTURES / "night_manifest.json"])
    assert len(comparisons) == 1
    item = comparisons[0]
    assert item.reference.provider == "sleepscope"
    assert item.comparison.provider == "fitbit"
    assert item.reference.duration_min > 0
    assert item.comparison.asleep_min > 0


def test_discover_directory():
    paths = discover_inputs(FIXTURES)
    assert paths == [FIXTURES / "night_manifest.json"]


def test_timelines_and_hypnogram(tmp_path: Path):
    comparisons = compare_many([FIXTURES / "night_manifest.json"])
    text = format_console_report(comparisons)
    assert "Sleep / Awake" in text
    assert "SleepScope" in text

    timelines = write_comparison_timelines(comparisons, tmp_path / "timelines")
    assert len(timelines) == 2
    assert all(path.exists() for path in timelines)

    plots = write_hypnogram_plots(comparisons, tmp_path / "plots")
    assert len(plots) == 1
    assert plots[0].exists()

from __future__ import annotations

from pathlib import Path

from sleep_analyzer.compare import compare_many, discover_inputs, parse_night_manifest
from sleep_analyzer.report import format_console_report, rollup_by_provider, write_plots

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_and_compare_night_manifest():
    manifest = parse_night_manifest(FIXTURES / "night_manifest.json")
    assert manifest.reference.provider == "sleepscope"
    assert manifest.reference.path.endswith(".csv")
    assert manifest.comparisons[0].provider == "fitbit"

    deltas = compare_many([FIXTURES / "night_manifest.json"])
    assert len(deltas) == 1
    delta = deltas[0]
    assert delta.reference.provider == "sleepscope"
    assert delta.comparison.provider == "fitbit"
    assert delta.reference.duration_min > 0
    assert delta.comparison.duration_min > 0


def test_discover_directory():
    paths = discover_inputs(FIXTURES)
    assert paths == [FIXTURES / "night_manifest.json"]


def test_rollup_and_report(tmp_path: Path):
    deltas = compare_many([FIXTURES / "night_manifest.json"])
    rollups = rollup_by_provider(deltas)
    assert "fitbit" in rollups
    text = format_console_report(deltas, rollups)
    assert "SleepScope vs wearable" in text
    assert "fitbit" in text

    plots = write_plots(deltas, tmp_path / "plots")
    assert plots
    assert all(path.exists() for path in plots)

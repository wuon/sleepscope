from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from sleep_analyzer.loaders import get_loader, registered_providers
from sleep_analyzer.metrics import compare_sessions
from sleep_analyzer.models import DataSource, NightComparison, NightManifest

_COMPARISON_PROVIDERS = frozenset({"fitbit", "apple_watch", "oura"})


def load_json(path: Path) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_path(base: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def parse_night_manifest(path: Path) -> NightManifest:
    path = Path(path).resolve()
    payload = load_json(path)

    if not isinstance(payload, dict):
        raise ValueError(f"{path}: night manifest must be a JSON object")

    if "nights" in payload:
        raise ValueError(
            f"{path}: looks like an experiment index (has 'nights'). "
            "Pass it to the CLI as an experiment file, not as a night manifest."
        )

    reference_raw = payload.get("reference")
    comparisons_raw = payload.get("comparisons")
    if not isinstance(reference_raw, dict):
        raise ValueError(f"{path}: 'reference' must be an object with provider/path")
    if not isinstance(comparisons_raw, list) or not comparisons_raw:
        raise ValueError(f"{path}: 'comparisons' must be a non-empty array")

    reference = _parse_source(reference_raw, path, field="reference")
    if reference.provider != "sleepscope":
        raise ValueError(
            f"{path}: reference.provider must be 'sleepscope', got '{reference.provider}'"
        )

    comparisons = tuple(
        _parse_source(item, path, field=f"comparisons[{index}]")
        for index, item in enumerate(comparisons_raw)
    )
    if len(comparisons) != 1:
        raise ValueError(
            f"{path}: v1 requires exactly one comparison entry, got {len(comparisons)}"
        )
    comparison_provider = comparisons[0].provider
    if comparison_provider not in _COMPARISON_PROVIDERS:
        known = ", ".join(sorted(_COMPARISON_PROVIDERS))
        raise ValueError(
            f"{path}: comparisons[0].provider must be one of {{{known}}}, "
            f"got '{comparison_provider}'"
        )
    # Ensure the loader package is imported so registry checks stay in sync.
    if comparison_provider not in registered_providers():
        raise ValueError(
            f"{path}: no loader registered for comparison provider '{comparison_provider}'"
        )

    night_id = str(payload.get("id") or path.stem)
    date = payload.get("date")
    notes = payload.get("notes")
    if date is not None:
        date = str(date)
    if notes is not None:
        notes = str(notes)

    return NightManifest(
        id=night_id,
        date=date,
        notes=notes,
        reference=reference,
        comparisons=comparisons,
        path=str(path),
    )


def discover_inputs(target: Path) -> list[Path]:
    """Return night manifest paths from a night file, experiment index, or directory."""
    target = Path(target).resolve()
    if target.is_dir():
        candidates = sorted(target.glob("*.json"))
        nights = [path for path in candidates if _looks_like_night_manifest(path)]
        if not nights:
            raise FileNotFoundError(f"No JSON night manifests found in {target}")
        return nights

    if not target.is_file():
        raise FileNotFoundError(target)

    payload = load_json(target)
    if isinstance(payload, dict) and "nights" in payload:
        nights_raw = payload["nights"]
        if not isinstance(nights_raw, list) or not nights_raw:
            raise ValueError(f"{target}: experiment 'nights' must be a non-empty array")
        result: list[Path] = []
        for index, item in enumerate(nights_raw):
            if not isinstance(item, str):
                raise ValueError(f"{target}: nights[{index}] must be a path string")
            result.append(resolve_path(target.parent, item))
        return result

    return [target]


def _looks_like_night_manifest(path: Path) -> bool:
    try:
        payload = load_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and "reference" in payload
        and "comparisons" in payload
        and "nights" not in payload
    )


def compare_night(manifest: NightManifest) -> list[NightComparison]:
    if not manifest.path:
        raise ValueError("NightManifest.path is required to resolve relative data paths")
    base = Path(manifest.path).parent

    ref_loader = get_loader(manifest.reference.provider)
    reference = ref_loader.load(resolve_path(base, manifest.reference.path))

    results: list[NightComparison] = []
    for source in manifest.comparisons:
        cmp_loader = get_loader(source.provider)
        comparison = cmp_loader.load(
            resolve_path(base, source.path),
            day=source.day,
        )
        results.append(
            compare_sessions(
                reference,
                comparison,
                night_id=manifest.id,
                date=manifest.date,
                notes=manifest.notes,
            )
        )
    return results


def compare_many(manifest_paths: Iterable[Path]) -> list[NightComparison]:
    results: list[NightComparison] = []
    for path in manifest_paths:
        manifest = parse_night_manifest(path)
        results.extend(compare_night(manifest))
    return results


def _parse_source(raw: Any, path: Path, *, field: str) -> DataSource:
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: {field} must be an object")
    provider = raw.get("provider")
    source_path = raw.get("path")
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError(f"{path}: {field}.provider must be a non-empty string")
    if not isinstance(source_path, str) or not source_path.strip():
        raise ValueError(f"{path}: {field}.path must be a non-empty string")
    day_raw = raw.get("day")
    day: str | None
    if day_raw is None:
        day = None
    elif isinstance(day_raw, str) and day_raw.strip():
        day = day_raw.strip()
    else:
        raise ValueError(f"{path}: {field}.day must be a non-empty YYYY-MM-DD string")
    return DataSource(
        provider=provider.strip().lower(),
        path=source_path.strip(),
        day=day,
    )

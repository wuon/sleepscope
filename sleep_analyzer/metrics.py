from __future__ import annotations

from sleep_analyzer.models import BinarySession, NightComparison
from sleep_analyzer.timeline import EpochTimeline, collapse_phone_timeline


def build_binary_session(
    *,
    provider: str,
    timeline: EpochTimeline,
    binary: bool = True,
) -> BinarySession:
    """Wrap a timeline as a BinarySession (collapsing phone 3-stage if needed)."""
    if not timeline.epochs:
        raise ValueError(f"{provider}: timeline has no epochs")
    working = collapse_phone_timeline(timeline) if not binary else timeline
    working.provider = provider
    return BinarySession(provider=provider, timeline=working)


def compare_sessions(
    reference: BinarySession,
    comparison: BinarySession,
    *,
    night_id: str,
    date: str | None = None,
    notes: str | None = None,
) -> NightComparison:
    return NightComparison(
        night_id=night_id,
        reference=reference,
        comparison=comparison,
        date=date,
        notes=notes,
    )

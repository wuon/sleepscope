from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from sleep_analyzer.models import BinarySession, NightComparison
from sleep_analyzer.timeline import BinaryLabel, Epoch, EpochTimeline, ensure_aware


# Lane colors — SleepScope vs Fitbit, Awake vs Sleep.
COLORS = {
    ("sleepscope", BinaryLabel.AWAKE.value): "#F2A7C2",
    ("sleepscope", BinaryLabel.SLEEP.value): "#5B8DEF",
    ("fitbit", BinaryLabel.AWAKE.value): "#E85D75",
    ("fitbit", BinaryLabel.SLEEP.value): "#2DD4BF",
}


def format_console_report(comparisons: Sequence[NightComparison]) -> str:
    lines: list[str] = []
    lines.append("SleepScope vs Fitbit — Sleep / Awake timelines")
    lines.append("=" * 64)
    lines.append("")
    for item in comparisons:
        ref = item.reference
        cmp = item.comparison
        lines.append(f"Night: {item.night_id}")
        lines.append(
            f"  SleepScope  Sleep {ref.asleep_min:6.1f} min   Awake {ref.awake_min:6.1f} min"
        )
        lines.append(
            f"  {cmp.provider:<10} Sleep {cmp.asleep_min:6.1f} min   "
            f"Awake {cmp.awake_min:6.1f} min"
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_timeline_json(session: BinarySession, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(session.to_dict(), handle, indent=2)
        handle.write("\n")
    return path


def write_comparison_timelines(
    comparisons: Sequence[NightComparison],
    output_dir: Path,
) -> list[Path]:
    """Write the two primary outputs: SleepScope and Fitbit Sleep/Awake timelines."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for item in comparisons:
        ref_path = output_dir / f"{item.night_id}_sleepscope_timeline.json"
        cmp_path = output_dir / f"{item.night_id}_{item.comparison.provider}_timeline.json"
        written.append(write_timeline_json(item.reference, ref_path))
        written.append(write_timeline_json(item.comparison, cmp_path))
    return written


def write_hypnogram_plots(
    comparisons: Sequence[NightComparison],
    output_dir: Path,
) -> list[Path]:
    """One condensed Awake/Sleep hypnogram per night comparing both providers."""
    if not comparisons:
        return []

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle
    from matplotlib.lines import Line2D

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for item in comparisons:
        path = output_dir / f"{item.night_id}_hypnogram.png"
        _draw_comparison_hypnogram(item, path, plt, mdates, FancyBboxPatch, Rectangle, Line2D)
        written.append(path)
    return written


def _draw_comparison_hypnogram(
    item: NightComparison,
    path: Path,
    plt,
    mdates,
    FancyBboxPatch,
    Rectangle,
    Line2D,
) -> None:
    ref = item.reference
    cmp = _align_session_to_reference(item.comparison, item.reference)

    fig, ax = plt.subplots(figsize=(14, 4.5))
    fig.patch.set_facecolor("#0B1220")
    ax.set_facecolor("#0B1220")

    lane_y = {
        BinaryLabel.AWAKE.value: 1.0,
        BinaryLabel.SLEEP.value: 0.0,
    }
    lane_half = 0.18
    provider_offset = {
        "sleepscope": 0.08,
        cmp.provider: -0.08,
    }

    t_min = _to_plot_time(min(ref.start, cmp.start))
    t_max = _to_plot_time(max(ref.end, cmp.end))
    if t_max <= t_min:
        t_max = t_min + timedelta(minutes=30)

    x_min = mdates.date2num(t_min)
    x_max = mdates.date2num(t_max)

    for label, y in lane_y.items():
        track = FancyBboxPatch(
            (x_min, y - 0.28),
            max(x_max - x_min, 1e-6),
            0.56,
            boxstyle="round,pad=0.01,rounding_size=0.08",
            linewidth=0,
            facecolor="#1A2336",
            zorder=0,
        )
        ax.add_patch(track)

    for session in (ref, cmp):
        offset = provider_offset.get(session.provider, 0.0)
        _draw_session_blocks(ax, session, lane_y, lane_half, offset, mdates, Rectangle)
        _draw_session_connectors(ax, session, lane_y, offset, mdates)

    for label, y in lane_y.items():
        ref_min = ref.awake_min if label == BinaryLabel.AWAKE.value else ref.asleep_min
        cmp_min = cmp.awake_min if label == BinaryLabel.AWAKE.value else cmp.asleep_min
        ax.text(
            -0.02,
            y,
            f"{label}\nSS {_fmt_minutes(ref_min)}  ·  FB {_fmt_minutes(cmp_min)}",
            transform=ax.get_yaxis_transform(),
            ha="right",
            va="center",
            color="#E8EEF8",
            fontsize=10,
            fontweight="medium",
            clip_on=False,
        )

    ax.set_ylim(-0.55, 1.55)
    ax.set_xlim(x_min, x_max)
    _configure_time_axis(ax, mdates, t_min, t_max)
    ax.tick_params(axis="x", colors="#9AA8C0", labelsize=9)
    ax.tick_params(axis="y", left=False, labelleft=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(
        f"{item.night_id}  —  SleepScope vs {cmp.provider}",
        color="#E8EEF8",
        fontsize=12,
        pad=12,
        loc="left",
    )

    legend = [
        Line2D([0], [0], color=COLORS[("sleepscope", BinaryLabel.AWAKE.value)], lw=6, label="SleepScope Awake"),
        Line2D([0], [0], color=COLORS[("sleepscope", BinaryLabel.SLEEP.value)], lw=6, label="SleepScope Sleep"),
        Line2D(
            [0],
            [0],
            color=COLORS.get((cmp.provider, BinaryLabel.AWAKE.value), "#E85D75"),
            lw=6,
            label=f"{cmp.provider} Awake",
        ),
        Line2D(
            [0],
            [0],
            color=COLORS.get((cmp.provider, BinaryLabel.SLEEP.value), "#2DD4BF"),
            lw=6,
            label=f"{cmp.provider} Sleep",
        ),
    ]
    ax.legend(
        handles=legend,
        loc="upper right",
        frameon=False,
        labelcolor="#C5D0E0",
        fontsize=8,
        ncol=2,
    )

    fig.tight_layout()
    fig.savefig(path, dpi=140, facecolor=fig.get_facecolor())
    plt.close(fig)


def _configure_time_axis(ax, mdates, t_min: datetime, t_max: datetime) -> None:
    """Use hour/minute ticks so overnight windows don't collapse to midnight labels."""
    span_hours = max((t_max - t_min).total_seconds() / 3600.0, 1 / 60)
    if span_hours <= 3:
        ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    elif span_hours <= 16:
        interval = 1 if span_hours <= 8 else 2
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=interval))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    else:
        interval = max(1, int(round(span_hours / 8)))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=interval))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))


def _align_session_to_reference(session: BinarySession, reference: BinarySession) -> BinarySession:
    """Shift a session onto the reference clock when the two barely overlap."""
    ref_start = ensure_aware(reference.start)
    ref_end = ensure_aware(reference.end)
    sess_start = ensure_aware(session.start)
    sess_end = ensure_aware(session.end)

    overlap_start = max(ref_start, sess_start)
    overlap_end = min(ref_end, sess_end)
    overlap_min = max(0.0, (overlap_end - overlap_start).total_seconds() / 60.0)
    if overlap_min >= 15.0:
        return session

    shift = ref_start - sess_start
    shifted = EpochTimeline(
        epochs=[
            Epoch(start=ensure_aware(epoch.start) + shift, label=epoch.label)
            for epoch in session.timeline.epochs
        ],
        provider=session.provider,
    )
    return BinarySession(provider=session.provider, timeline=shifted)


def _to_plot_time(value: datetime) -> datetime:
    """Naive UTC datetime for matplotlib date converters."""
    aware = ensure_aware(value).astimezone(timezone.utc)
    return aware.replace(tzinfo=None)


def _draw_session_blocks(ax, session: BinarySession, lane_y, lane_half, offset, mdates, Rectangle) -> None:
    runs = _contiguous_runs(session.timeline)
    for label, start, end in runs:
        y = lane_y[label] + offset
        color = COLORS.get((session.provider, label), "#888888")
        x0 = mdates.date2num(_to_plot_time(start))
        x1 = mdates.date2num(_to_plot_time(end))
        ax.add_patch(
            Rectangle(
                (x0, y - lane_half * 0.55),
                max(x1 - x0, 1e-6),
                lane_half * 1.1,
                linewidth=0,
                facecolor=color,
                alpha=0.92,
                zorder=2,
                clip_on=True,
            )
        )


def _draw_session_connectors(ax, session: BinarySession, lane_y, offset, mdates) -> None:
    runs = _contiguous_runs(session.timeline)
    if len(runs) < 2:
        return
    for index in range(len(runs) - 1):
        label_a, _start_a, end_a = runs[index]
        label_b, start_b, _end_b = runs[index + 1]
        if label_a == label_b:
            continue
        y0 = lane_y[label_a] + offset
        y1 = lane_y[label_b] + offset
        x = mdates.date2num(_to_plot_time(end_a))
        x_b = mdates.date2num(_to_plot_time(start_b))
        x_mid = (x + x_b) / 2.0
        color = COLORS.get((session.provider, label_b), "#666666")
        ax.plot([x_mid, x_mid], [y0, y1], color=color, linewidth=1.2, alpha=0.7, zorder=1)


def _contiguous_runs(
    timeline: EpochTimeline,
) -> list[tuple[str, datetime, datetime]]:
    if not timeline.epochs:
        return []
    runs: list[tuple[str, datetime, datetime]] = []
    current = timeline.epochs[0].label
    start = timeline.epochs[0].start
    end = timeline.epochs[0].end
    for epoch in timeline.epochs[1:]:
        if epoch.label == current:
            end = epoch.end
            continue
        runs.append((current, start, end))
        current = epoch.label
        start = epoch.start
        end = epoch.end
    runs.append((current, start, end))
    return runs


def _fmt_minutes(minutes: float) -> str:
    total = int(round(minutes))
    hours, mins = divmod(total, 60)
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"

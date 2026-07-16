from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import stats

from sleep_analyzer.models import MetricRollup, NightDelta

DELTA_METRICS = (
    "duration_min",
    "deep_min",
    "light_min",
    "rem_min",
    "awake_min",
    "asleep_min",
    "efficiency",
    "deep_pct",
    "light_pct",
    "rem_pct",
    "awake_pct",
    "start_abs_min",
    "end_abs_min",
)

PRIMARY_PLOT_METRICS = ("deep_min", "rem_min", "efficiency")


def deltas_to_dataframe(deltas: Sequence[NightDelta]) -> pd.DataFrame:
    if not deltas:
        return pd.DataFrame()
    return pd.DataFrame([delta.to_row() for delta in deltas])


def rollup_by_provider(deltas: Sequence[NightDelta]) -> dict[str, list[MetricRollup]]:
    grouped: dict[str, list[NightDelta]] = defaultdict(list)
    for delta in deltas:
        grouped[delta.comparison_provider].append(delta)

    result: dict[str, list[MetricRollup]] = {}
    for provider, items in sorted(grouped.items()):
        result[provider] = [_rollup_metric(items, metric) for metric in DELTA_METRICS]
    return result


def _rollup_metric(items: Sequence[NightDelta], metric: str) -> MetricRollup:
    delta_key = f"{metric}_delta"
    ref_key = f"ref_{metric}" if not metric.endswith("_pct") else None
    cmp_key = f"cmp_{metric}" if not metric.endswith("_pct") else None

    delta_values = np.array([getattr(item, delta_key) for item in items], dtype=float)
    n = len(delta_values)
    mean_bias = float(np.mean(delta_values))
    mae = float(np.mean(np.abs(delta_values)))
    rmse = float(np.sqrt(np.mean(np.square(delta_values))))

    pearson_r = None
    spearman_r = None
    if n >= 3 and ref_key and cmp_key and hasattr(items[0].reference, metric):
        ref_vals = np.array([getattr(item.reference, metric) for item in items], dtype=float)
        cmp_vals = np.array([getattr(item.comparison, metric) for item in items], dtype=float)
        if np.std(ref_vals) > 0 and np.std(cmp_vals) > 0:
            pearson_r = float(stats.pearsonr(ref_vals, cmp_vals).statistic)
            spearman_r = float(stats.spearmanr(ref_vals, cmp_vals).statistic)
    elif n >= 3 and metric.endswith("_pct"):
        stage = metric.removesuffix("_pct")
        ref_vals = np.array([item.reference.stage_pct(stage) for item in items], dtype=float)
        cmp_vals = np.array([item.comparison.stage_pct(stage) for item in items], dtype=float)
        if np.std(ref_vals) > 0 and np.std(cmp_vals) > 0:
            pearson_r = float(stats.pearsonr(ref_vals, cmp_vals).statistic)
            spearman_r = float(stats.spearmanr(ref_vals, cmp_vals).statistic)

    return MetricRollup(
        metric=metric,
        n=n,
        mean_bias=mean_bias,
        mae=mae,
        rmse=rmse,
        pearson_r=pearson_r,
        spearman_r=spearman_r,
        exploratory=n < 10,
    )


def format_console_report(
    deltas: Sequence[NightDelta],
    rollups: dict[str, list[MetricRollup]],
) -> str:
    lines: list[str] = []
    lines.append("SleepScope vs wearable — session comparison")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Nights compared: {len(deltas)}")
    lines.append("")

    if deltas:
        lines.append("Per-night deltas (SleepScope − wearable)")
        lines.append("-" * 72)
        header = (
            f"{'night':<22} {'provider':<10} {'deepΔ':>8} {'remΔ':>8} "
            f"{'lightΔ':>8} {'awakeΔ':>8} {'effΔ':>8}"
        )
        lines.append(header)
        for delta in deltas:
            lines.append(
                f"{delta.night_id:<22} {delta.comparison_provider:<10} "
                f"{delta.deep_min_delta:>8.1f} {delta.rem_min_delta:>8.1f} "
                f"{delta.light_min_delta:>8.1f} {delta.awake_min_delta:>8.1f} "
                f"{delta.efficiency_delta:>8.3f}"
            )
        lines.append("")

    for provider, metrics in rollups.items():
        lines.append(f"Rollup vs {provider}")
        lines.append("-" * 72)
        n = metrics[0].n if metrics else 0
        flag = "exploratory (n < 10)" if n < 10 else "target sample size met"
        lines.append(f"n = {n}  [{flag}]")
        lines.append(
            f"{'metric':<16} {'bias':>10} {'MAE':>10} {'RMSE':>10} "
            f"{'pearson':>10} {'spearman':>10}"
        )
        for item in metrics:
            pearson = f"{item.pearson_r:.3f}" if item.pearson_r is not None else "n/a"
            spearman = f"{item.spearman_r:.3f}" if item.spearman_r is not None else "n/a"
            lines.append(
                f"{item.metric:<16} {item.mean_bias:>10.3f} {item.mae:>10.3f} "
                f"{item.rmse:>10.3f} {pearson:>10} {spearman:>10}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_csv(deltas: Sequence[NightDelta], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    deltas_to_dataframe(deltas).to_csv(path, index=False)


def write_rollup_csv(rollups: dict[str, list[MetricRollup]], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for provider, metrics in rollups.items():
        for item in metrics:
            rows.append(
                {
                    "comparison_provider": provider,
                    "metric": item.metric,
                    "n": item.n,
                    "mean_bias": item.mean_bias,
                    "mae": item.mae,
                    "rmse": item.rmse,
                    "pearson_r": item.pearson_r,
                    "spearman_r": item.spearman_r,
                    "exploratory": item.exploratory,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def write_plots(
    deltas: Sequence[NightDelta],
    output_dir: Path,
    metrics: Iterable[str] = PRIMARY_PLOT_METRICS,
) -> list[Path]:
    if not deltas:
        return []

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    by_provider: dict[str, list[NightDelta]] = defaultdict(list)
    for delta in deltas:
        by_provider[delta.comparison_provider].append(delta)

    for provider, items in by_provider.items():
        for metric in metrics:
            ref_vals = np.array([getattr(item.reference, metric) for item in items], dtype=float)
            cmp_vals = np.array([getattr(item.comparison, metric) for item in items], dtype=float)

            # Scatter
            scatter_path = output_dir / f"{provider}_{metric}_scatter.png"
            fig, ax = plt.subplots(figsize=(6, 6))
            ax.scatter(cmp_vals, ref_vals, c="#1f4e79", alpha=0.8)
            lo = float(min(ref_vals.min(), cmp_vals.min()))
            hi = float(max(ref_vals.max(), cmp_vals.max()))
            pad = (hi - lo) * 0.05 if hi > lo else 1.0
            ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], "--", color="#888888")
            ax.set_xlabel(f"{provider} {metric}")
            ax.set_ylabel(f"sleepscope {metric}")
            ax.set_title(f"SleepScope vs {provider}: {metric}")
            fig.tight_layout()
            fig.savefig(scatter_path, dpi=120)
            plt.close(fig)
            written.append(scatter_path)

            # Bland-Altman
            ba_path = output_dir / f"{provider}_{metric}_bland_altman.png"
            means = (ref_vals + cmp_vals) / 2.0
            diffs = ref_vals - cmp_vals
            md = float(np.mean(diffs))
            sd = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0
            fig, ax = plt.subplots(figsize=(7, 5))
            ax.scatter(means, diffs, c="#1f4e79", alpha=0.8)
            ax.axhline(md, color="#c44e52", linestyle="-", label=f"mean bias {md:.2f}")
            ax.axhline(md + 1.96 * sd, color="#888888", linestyle="--", label="+1.96 SD")
            ax.axhline(md - 1.96 * sd, color="#888888", linestyle="--", label="-1.96 SD")
            ax.set_xlabel(f"mean ({metric})")
            ax.set_ylabel(f"SleepScope − {provider}")
            ax.set_title(f"Bland-Altman: {metric} vs {provider}")
            ax.legend(loc="best", fontsize=8)
            fig.tight_layout()
            fig.savefig(ba_path, dpi=120)
            plt.close(fig)
            written.append(ba_path)

    return written

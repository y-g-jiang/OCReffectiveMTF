from __future__ import annotations

import argparse
import csv
import os
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors as mcolors

from mtfsnr_sim.analysis import write_results_csv
from mtfsnr_sim.chart_generator import (
    apply_integer_shift,
    build_phase_offsets,
    generate_permutation_strings,
    render_text_image,
)
from mtfsnr_sim.config import build_config
from mtfsnr_sim.ocr_runner import run_tesseract
from mtfsnr_sim.sensor_model import simulate_capture


COUPLED_CONDITION = "coupled_fill_factor"
SNR_ONLY_CONDITION = "snr_only_matched"


def _format_seconds(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class ProgressTracker:
    def __init__(self, total: int) -> None:
        self.total = max(1, total)
        self.completed = 0
        self.started_at = time.perf_counter()
        self.next_report_ratio = 0.01
        self.last_report_at = self.started_at

    def update_many(self, increment: int, context: str) -> None:
        self.completed += increment
        now = time.perf_counter()
        ratio = self.completed / self.total
        should_report = (
            ratio >= self.next_report_ratio
            or self.completed >= self.total
            or (now - self.last_report_at) >= 15.0
        )
        if not should_report:
            return

        elapsed = now - self.started_at
        rate = self.completed / elapsed if elapsed > 0 else 0.0
        remaining = max(0, self.total - self.completed)
        eta = remaining / rate if rate > 0 else 0.0
        print(
            f"[{ratio:6.1%}] {self.completed}/{self.total} "
            f"elapsed={_format_seconds(elapsed)} eta={_format_seconds(eta)} "
            f"| {context}",
            flush=True,
        )
        while ratio >= self.next_report_ratio:
            self.next_report_ratio += 0.01
        self.last_report_at = now


def _cer(reference: str, hypothesis: str) -> float:
    rows = len(reference) + 1
    cols = len(hypothesis) + 1
    dp = [[0] * cols for _ in range(rows)]

    for i in range(rows):
        dp[i][0] = i
    for j in range(cols):
        dp[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )

    return dp[-1][-1] / max(1, len(reference))


@dataclass(slots=True)
class ComparisonTask:
    task_index: int
    char_height_px: int
    font_path: Path
    text: str
    phase_x: int
    phase_y: int
    base_mu_p: int
    rho_values: tuple[float, ...]
    noise_repeats: int
    oversample: int
    padding_px: int
    eta_si: float
    read_noise_e: float
    optical_sigma_hr: float
    quant_bits: int
    ocr_upscale: int
    tesseract_path: Path
    whitelist: str
    psm: int
    random_seed: int


@lru_cache(maxsize=256)
def _render_cached(
    font_path: str,
    text: str,
    char_height_px: int,
    oversample: int,
    padding_px: int,
) -> np.ndarray:
    scene = render_text_image(
        text=text,
        font_path=Path(font_path),
        char_height_px=char_height_px,
        oversample=oversample,
        padding_px=padding_px,
    )
    scene.setflags(write=False)
    return scene


@lru_cache(maxsize=1024)
def _shifted_scene_cached(
    font_path: str,
    text: str,
    char_height_px: int,
    oversample: int,
    padding_px: int,
    phase_x: int,
    phase_y: int,
) -> np.ndarray:
    base_scene = _render_cached(font_path, text, char_height_px, oversample, padding_px)
    shifted = apply_integer_shift(base_scene, phase_x, phase_y)
    shifted.setflags(write=False)
    return shifted


def evaluate_comparison_task(task: ComparisonTask) -> list[dict[str, object]]:
    rng = np.random.default_rng(task.random_seed + task.task_index * 1_000_003)
    shifted_scene = _shifted_scene_cached(
        str(task.font_path),
        task.text,
        task.char_height_px,
        task.oversample,
        task.padding_px,
        task.phase_x,
        task.phase_y,
    )

    rows: list[dict[str, object]] = []
    for rho in task.rho_values:
        matched_mu_p = task.base_mu_p * rho
        for noise_repeat in range(task.noise_repeats):
            coupled_capture = simulate_capture(
                scene_hr=shifted_scene,
                rho=rho,
                mu_p=task.base_mu_p,
                eta_si=task.eta_si,
                read_noise_e=task.read_noise_e,
                oversample=task.oversample,
                optical_sigma_hr=task.optical_sigma_hr,
                quant_bits=task.quant_bits,
                ocr_upscale=task.ocr_upscale,
                rng=rng,
                ideal_snr=False,
            )
            coupled_ocr = run_tesseract(
                image_u8=coupled_capture.ocr_ready_image_u8,
                tesseract_path=task.tesseract_path,
                whitelist=task.whitelist,
                psm=task.psm,
            )
            coupled_err = _cer(task.text, coupled_ocr.text)
            rows.append(
                {
                    "condition": COUPLED_CONDITION,
                    "base_mu_p": task.base_mu_p,
                    "matched_mu_p": round(float(matched_mu_p), 6),
                    "rho": rho,
                    "char_height_px": task.char_height_px,
                    "font_name": task.font_path.name,
                    "text": task.text,
                    "phase_x": task.phase_x,
                    "phase_y": task.phase_y,
                    "noise_repeat": noise_repeat,
                    "control_blur_rho": rho,
                    "qe_total": round(coupled_capture.qe_total, 6),
                    "mtf_nyquist": round(coupled_capture.mtf_nyquist, 6),
                    "aperture_f50_cpp": round(coupled_capture.aperture_f50_cpp, 6),
                    "ocr_text": coupled_ocr.text,
                    "cer": round(coupled_err, 6),
                    "char_acc": round(1.0 - coupled_err, 6),
                }
            )

            snr_only_capture = simulate_capture(
                scene_hr=shifted_scene,
                rho=1.0,
                mu_p=matched_mu_p,
                eta_si=task.eta_si,
                read_noise_e=task.read_noise_e,
                oversample=task.oversample,
                optical_sigma_hr=task.optical_sigma_hr,
                quant_bits=task.quant_bits,
                ocr_upscale=task.ocr_upscale,
                rng=rng,
                ideal_snr=False,
            )
            snr_only_ocr = run_tesseract(
                image_u8=snr_only_capture.ocr_ready_image_u8,
                tesseract_path=task.tesseract_path,
                whitelist=task.whitelist,
                psm=task.psm,
            )
            snr_only_err = _cer(task.text, snr_only_ocr.text)
            rows.append(
                {
                    "condition": SNR_ONLY_CONDITION,
                    "base_mu_p": task.base_mu_p,
                    "matched_mu_p": round(float(matched_mu_p), 6),
                    "rho": rho,
                    "char_height_px": task.char_height_px,
                    "font_name": task.font_path.name,
                    "text": task.text,
                    "phase_x": task.phase_x,
                    "phase_y": task.phase_y,
                    "noise_repeat": noise_repeat,
                    "control_blur_rho": 1.0,
                    "qe_total": round(snr_only_capture.qe_total, 6),
                    "mtf_nyquist": round(snr_only_capture.mtf_nyquist, 6),
                    "aperture_f50_cpp": round(snr_only_capture.aperture_f50_cpp, 6),
                    "ocr_text": snr_only_ocr.text,
                    "cer": round(snr_only_err, 6),
                    "char_acc": round(1.0 - snr_only_err, 6),
                }
            )
    return rows


def aggregate_condition_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int, float, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row["condition"]),
            int(row["base_mu_p"]),
            float(row["rho"]),
            int(row["char_height_px"]),
        )
        grouped[key].append(row)

    aggregate_rows: list[dict[str, object]] = []
    for (condition, base_mu_p, rho, char_height_px), items in sorted(grouped.items()):
        cer_values = np.array([float(item["cer"]) for item in items], dtype=float)
        char_acc_values = np.array([float(item["char_acc"]) for item in items], dtype=float)
        matched_mu_values = np.array([float(item["matched_mu_p"]) for item in items], dtype=float)
        aggregate_rows.append(
            {
                "condition": condition,
                "base_mu_p": base_mu_p,
                "rho": rho,
                "char_height_px": char_height_px,
                "matched_mu_p": float(matched_mu_values.mean()),
                "mean_cer": float(cer_values.mean()),
                "mean_char_acc": float(char_acc_values.mean()),
                "n_eval": len(items),
                "qe_total": float(items[0]["qe_total"]),
                "mtf_nyquist": float(items[0]["mtf_nyquist"]),
                "aperture_f50_cpp": float(items[0]["aperture_f50_cpp"]),
                "control_blur_rho": float(items[0]["control_blur_rho"]),
            }
        )
    return aggregate_rows


def build_advantage_rows(aggregate_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    indexed: dict[tuple[str, int, float, int], dict[str, object]] = {}
    for row in aggregate_rows:
        key = (
            str(row["condition"]),
            int(row["base_mu_p"]),
            float(row["rho"]),
            int(row["char_height_px"]),
        )
        indexed[key] = row

    advantage_rows: list[dict[str, object]] = []
    keys = sorted(
        {
            (
                int(row["base_mu_p"]),
                float(row["rho"]),
                int(row["char_height_px"]),
            )
            for row in aggregate_rows
        }
    )
    for base_mu_p, rho, char_height_px in keys:
        coupled = indexed[(COUPLED_CONDITION, base_mu_p, rho, char_height_px)]
        snr_only = indexed[(SNR_ONLY_CONDITION, base_mu_p, rho, char_height_px)]
        advantage_rows.append(
            {
                "base_mu_p": base_mu_p,
                "rho": rho,
                "char_height_px": char_height_px,
                "matched_mu_p": float(coupled["matched_mu_p"]),
                "coupled_mean_char_acc": float(coupled["mean_char_acc"]),
                "snr_only_mean_char_acc": float(snr_only["mean_char_acc"]),
                "char_acc_advantage": float(coupled["mean_char_acc"]) - float(snr_only["mean_char_acc"]),
                "coupled_mean_cer": float(coupled["mean_cer"]),
                "snr_only_mean_cer": float(snr_only["mean_cer"]),
                "n_eval": int(coupled["n_eval"]),
                "coupled_mtf_nyquist": float(coupled["mtf_nyquist"]),
                "snr_only_mtf_nyquist": float(snr_only["mtf_nyquist"]),
            }
        )
    return advantage_rows


def build_paired_statistics(detail_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    paired_index: dict[tuple[int, float, int, int, int, int], dict[str, dict[str, object]]] = defaultdict(dict)
    for row in detail_rows:
        key = (
            int(row["base_mu_p"]),
            float(row["rho"]),
            int(row["char_height_px"]),
            int(row["phase_x"]),
            int(row["phase_y"]),
            int(row["noise_repeat"]),
        )
        paired_index[key][str(row["condition"])] = row

    grouped_pairs: dict[tuple[int, float, int], list[tuple[float, float]]] = defaultdict(list)
    for key, item in paired_index.items():
        if COUPLED_CONDITION not in item or SNR_ONLY_CONDITION not in item:
            continue
        base_mu_p, rho, char_height_px, _, _, _ = key
        coupled = float(item[COUPLED_CONDITION]["char_acc"])
        snr_only = float(item[SNR_ONLY_CONDITION]["char_acc"])
        grouped_pairs[(base_mu_p, rho, char_height_px)].append((coupled, snr_only))

    stats_rows: list[dict[str, object]] = []
    for (base_mu_p, rho, char_height_px), pairs in sorted(grouped_pairs.items()):
        coupled_values = np.array([pair[0] for pair in pairs], dtype=float)
        snr_only_values = np.array([pair[1] for pair in pairs], dtype=float)
        deltas = coupled_values - snr_only_values

        cov_value = 0.0
        corr_value = 0.0
        if len(pairs) > 1:
            cov_value = float(np.cov(coupled_values, snr_only_values, ddof=1)[0, 1])
            coupled_std = float(coupled_values.std(ddof=1))
            snr_only_std = float(snr_only_values.std(ddof=1))
            if coupled_std > 1e-12 and snr_only_std > 1e-12:
                corr_value = float(np.corrcoef(coupled_values, snr_only_values)[0, 1])

        stats_rows.append(
            {
                "base_mu_p": base_mu_p,
                "rho": rho,
                "char_height_px": char_height_px,
                "n_pairs": len(pairs),
                "paired_cov_char_acc": cov_value,
                "paired_corr_char_acc": corr_value,
                "paired_mean_delta": float(deltas.mean()),
                "paired_std_delta": float(deltas.std(ddof=1)) if len(pairs) > 1 else 0.0,
                "paired_win_rate": float(np.mean(deltas > 0.0)),
                "paired_tie_rate": float(np.mean(np.abs(deltas) < 1e-12)),
            }
        )
    return stats_rows


def write_best_advantage_table(advantage_rows: list[dict[str, object]], output_path: Path) -> None:
    mu_values = sorted({int(row["base_mu_p"]) for row in advantage_rows})
    heights = sorted({int(row["char_height_px"]) for row in advantage_rows})
    out_rows: list[dict[str, object]] = []
    for height in heights:
        row_out: dict[str, object] = {"char_height_px": height}
        for base_mu_p in mu_values:
            subset = [
                row
                for row in advantage_rows
                if int(row["char_height_px"]) == height and int(row["base_mu_p"]) == base_mu_p
            ]
            if not subset:
                row_out[str(base_mu_p)] = ""
                continue
            best = max(subset, key=lambda item: float(item["char_acc_advantage"]))
            row_out[str(base_mu_p)] = round(float(best["char_acc_advantage"]), 6)
        out_rows.append(row_out)
    write_results_csv(output_path, out_rows)


def plot_paired_metric_heatmap(
    paired_rows: list[dict[str, object]],
    metric_key: str,
    title: str,
    colorbar_label: str,
    output_path: Path,
) -> None:
    if not paired_rows:
        return

    mu_values = sorted({int(row["base_mu_p"]) for row in paired_rows})
    rho_values = sorted({float(row["rho"]) for row in paired_rows})
    grid = np.full((len(rho_values), len(mu_values)), np.nan, dtype=float)

    for r_idx, rho in enumerate(rho_values):
        for m_idx, base_mu_p in enumerate(mu_values):
            subset = [
                row
                for row in paired_rows
                if int(row["base_mu_p"]) == base_mu_p and abs(float(row["rho"]) - rho) < 1e-12
            ]
            if subset:
                grid[r_idx, m_idx] = float(subset[0][metric_key])

    if metric_key == "paired_cov_char_acc":
        vmax = float(np.nanmax(np.abs(grid))) if np.isfinite(grid).any() else 1.0
        vmax = max(vmax, 1e-6)
        norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
        cmap = "coolwarm"
    else:
        norm = None
        cmap = "viridis"

    fig, ax = plt.subplots(figsize=(max(12, len(mu_values) * 0.65), 7))
    im = ax.imshow(grid, cmap=cmap, norm=norm, aspect="auto")
    ax.set_title(title)
    ax.set_xlabel("Base mu_p")
    ax.set_ylabel("rho")
    ax.set_xticks(np.arange(len(mu_values)), labels=[str(v) for v in mu_values], rotation=45, ha="right")
    ax.set_yticks(np.arange(len(rho_values)), labels=[f"{v:.1f}" for v in rho_values])
    fig.colorbar(im, ax=ax, label=colorbar_label)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_advantage_heatmap(advantage_rows: list[dict[str, object]], output_path: Path) -> None:
    if not advantage_rows:
        return

    mu_values = sorted({int(row["base_mu_p"]) for row in advantage_rows})
    rho_values = sorted({float(row["rho"]) for row in advantage_rows})
    grid = np.full((len(rho_values), len(mu_values)), np.nan, dtype=float)

    for r_idx, rho in enumerate(rho_values):
        for m_idx, base_mu_p in enumerate(mu_values):
            subset = [
                row
                for row in advantage_rows
                if int(row["base_mu_p"]) == base_mu_p and abs(float(row["rho"]) - rho) < 1e-12
            ]
            if subset:
                grid[r_idx, m_idx] = float(subset[0]["char_acc_advantage"])

    vmax = float(np.nanmax(np.abs(grid))) if np.isfinite(grid).any() else 1.0
    vmax = max(vmax, 1e-6)
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)

    fig, ax = plt.subplots(figsize=(max(12, len(mu_values) * 0.65), 7))
    im = ax.imshow(grid, cmap="coolwarm", norm=norm, aspect="auto")
    ax.set_title("Coupled fill-factor loss minus SNR-only matched control")
    ax.set_xlabel("Base mu_p")
    ax.set_ylabel("rho")
    ax.set_xticks(np.arange(len(mu_values)), labels=[str(v) for v in mu_values], rotation=45, ha="right")
    ax.set_yticks(np.arange(len(rho_values)), labels=[f"{v:.1f}" for v in rho_values])
    fig.colorbar(im, ax=ax, label="char_acc advantage")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_selected_mu_curves(aggregate_rows: list[dict[str, object]], output_path: Path) -> None:
    if not aggregate_rows:
        return

    mu_values = sorted({int(row["base_mu_p"]) for row in aggregate_rows})
    rho_values = sorted({float(row["rho"]) for row in aggregate_rows})
    selected_indices = np.linspace(0, len(mu_values) - 1, min(5, len(mu_values)), dtype=int)
    selected_mu_values = [mu_values[idx] for idx in selected_indices]

    fig, axes = plt.subplots(len(selected_mu_values), 1, figsize=(9, 3.0 * len(selected_mu_values)), squeeze=False)
    for ax, base_mu_p in zip(axes.flat, selected_mu_values):
        coupled = [
            row for row in aggregate_rows
            if str(row["condition"]) == COUPLED_CONDITION and int(row["base_mu_p"]) == base_mu_p
        ]
        snr_only = [
            row for row in aggregate_rows
            if str(row["condition"]) == SNR_ONLY_CONDITION and int(row["base_mu_p"]) == base_mu_p
        ]
        coupled.sort(key=lambda item: float(item["rho"]))
        snr_only.sort(key=lambda item: float(item["rho"]))
        ax.plot(
            [float(row["rho"]) for row in coupled],
            [float(row["mean_char_acc"]) for row in coupled],
            marker="o",
            label="coupled fill-factor",
        )
        ax.plot(
            [float(row["rho"]) for row in snr_only],
            [float(row["mean_char_acc"]) for row in snr_only],
            marker="o",
            label="snr-only matched",
        )
        ax.set_title(f"base mu_p={base_mu_p}")
        ax.set_ylabel("mean char acc")
        ax.set_ylim(-0.02, 1.02)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="lower left")

    axes.flat[-1].set_xlabel("rho")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def write_summary_md(
    output_path: Path,
    text: str,
    mu_values: tuple[int, ...],
    rho_values: tuple[float, ...],
    advantage_rows: list[dict[str, object]],
    paired_rows: list[dict[str, object]],
) -> None:
    best_positive = max(advantage_rows, key=lambda row: float(row["char_acc_advantage"]))
    worst_negative = min(advantage_rows, key=lambda row: float(row["char_acc_advantage"]))
    mean_advantage = float(np.mean([float(row["char_acc_advantage"]) for row in advantage_rows]))
    mean_cov = float(np.mean([float(row["paired_cov_char_acc"]) for row in paired_rows])) if paired_rows else 0.0
    mean_corr = float(np.mean([float(row["paired_corr_char_acc"]) for row in paired_rows])) if paired_rows else 0.0

    lines = [
        "# Resolution Advantage Test",
        "",
        "## Assumption",
        "- `coupled_fill_factor`: `rho` controls both aperture blur and QE, so lower `rho` means higher MTF but lower signal.",
        "- `snr_only_matched`: aperture blur stays at `rho=1.0`, while photon budget is reduced to `base_mu_p * rho` so the mean signal matches the coupled case.",
        "- If `coupled_fill_factor` beats `snr_only_matched`, that indicates a real resolution advantage beyond a pure SNR penalty.",
        "",
        "## Setup",
        f"- text: `{text}`",
        f"- base mu grid: `{', '.join(str(v) for v in mu_values)}`",
        f"- rho grid: `{', '.join(f'{v:.1f}' for v in rho_values)}`",
        "",
        "## Aggregate",
        f"- mean char-accuracy advantage: `{mean_advantage:.6f}`",
        f"- mean paired covariance: `{mean_cov:.6f}`",
        f"- mean paired correlation: `{mean_corr:.6f}`",
        f"- best positive advantage: `mu_p={int(best_positive['base_mu_p'])}`, `rho={float(best_positive['rho']):.1f}`, `delta={float(best_positive['char_acc_advantage']):.6f}`",
        f"- worst negative advantage: `mu_p={int(worst_negative['base_mu_p'])}`, `rho={float(worst_negative['rho']):.1f}`, `delta={float(worst_negative['char_acc_advantage']):.6f}`",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare true fill-factor loss against an SNR-only matched control."
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/resolution_advantage_8px",
        help="Output root. Results are written under <output-dir>/baseline.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Process count. Defaults to CPU count.",
    )
    return parser.parse_args()


def _read_results_csv(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    parsed_rows: list[dict[str, object]] = []
    for row in rows:
        parsed: dict[str, object] = dict(row)
        for key in (
            "base_mu_p",
            "char_height_px",
            "phase_x",
            "phase_y",
            "noise_repeat",
        ):
            if key in parsed and parsed[key] != "":
                parsed[key] = int(float(parsed[key]))
        for key in (
            "matched_mu_p",
            "rho",
            "control_blur_rho",
            "qe_total",
            "mtf_nyquist",
            "aperture_f50_cpp",
            "cer",
            "char_acc",
        ):
            if key in parsed and parsed[key] != "":
                parsed[key] = float(parsed[key])
        parsed_rows.append(parsed)
    return parsed_rows


def run_postprocess_only(output_dir: Path) -> None:
    detail_rows = _read_results_csv(output_dir / "detail_results.csv")
    aggregate_rows = _read_results_csv(output_dir / "aggregate_by_condition.csv")
    advantage_rows = _read_results_csv(output_dir / "advantage_summary.csv")
    paired_rows = build_paired_statistics(detail_rows)

    write_results_csv(output_dir / "paired_statistics.csv", paired_rows)
    plot_paired_metric_heatmap(
        paired_rows,
        metric_key="paired_cov_char_acc",
        title="Paired covariance of char-accuracy",
        colorbar_label="cov(char_acc)",
        output_path=output_dir / "paired_cov_heatmap.png",
    )
    plot_paired_metric_heatmap(
        paired_rows,
        metric_key="paired_corr_char_acc",
        title="Paired correlation of char-accuracy",
        colorbar_label="corr(char_acc)",
        output_path=output_dir / "paired_corr_heatmap.png",
    )

    summary_path = output_dir / "SUMMARY.md"
    text = ""
    if detail_rows:
        text = str(detail_rows[0]["text"])
    mu_values = tuple(sorted({int(row["base_mu_p"]) for row in advantage_rows}))
    rho_values = tuple(sorted({float(row["rho"]) for row in advantage_rows}))
    write_summary_md(
        summary_path,
        text=text,
        mu_values=mu_values,
        rho_values=rho_values,
        advantage_rows=advantage_rows,
        paired_rows=paired_rows,
    )
    print(f"Postprocessed paired statistics under: {output_dir.resolve()}")


def main() -> None:
    args = _parse_args()
    config = build_config("baseline", args.output_dir)
    config.char_heights_px = (8,)
    config.mu_p_values = (
        4, 5, 6, 7, 8, 10, 11, 13, 16, 19, 23, 27, 32, 38, 45, 54, 64, 76, 91, 108, 128, 152, 181, 215, 256,
    )
    config.whitelist = "023456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    config.samples_per_condition = 1
    config.noise_repeats = 2
    config.phase_count = 5
    config.output_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(config.random_seed)
    texts = generate_permutation_strings(rng=rng, count=config.samples_per_condition, alphabet=config.whitelist)
    text = texts[0]
    phase_offsets = build_phase_offsets(config.oversample, config.phase_count)

    tasks: list[ComparisonTask] = []
    task_index = 0
    for char_height_px in config.char_heights_px:
        for font_path in config.fonts:
            for phase_x in phase_offsets:
                for phase_y in phase_offsets:
                    for base_mu_p in config.mu_p_values:
                        tasks.append(
                            ComparisonTask(
                                task_index=task_index,
                                char_height_px=char_height_px,
                                font_path=font_path,
                                text=text,
                                phase_x=phase_x,
                                phase_y=phase_y,
                                base_mu_p=base_mu_p,
                                rho_values=config.rho_values,
                                noise_repeats=config.noise_repeats,
                                oversample=config.oversample,
                                padding_px=config.padding_px,
                                eta_si=config.eta_si,
                                read_noise_e=config.read_noise_e,
                                optical_sigma_hr=config.optical_sigma_hr,
                                quant_bits=config.quant_bits,
                                ocr_upscale=config.ocr_upscale,
                                tesseract_path=config.tesseract_path,
                                whitelist=config.whitelist,
                                psm=config.psm,
                                random_seed=config.random_seed,
                            )
                        )
                        task_index += 1

    workers = args.workers or max(1, os.cpu_count() or 1)
    evals_per_task = len(config.rho_values) * config.noise_repeats * 2
    total_evals = len(tasks) * evals_per_task
    print(
        f"Running {total_evals} OCR evaluations for matched-SNR comparison "
        f"using {workers} worker(s)."
    )
    progress = ProgressTracker(total_evals)

    detail_rows: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_task = {
            executor.submit(evaluate_comparison_task, task): task
            for task in tasks
        }
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            rows = future.result()
            detail_rows.extend(rows)
            progress.update_many(
                len(rows),
                f"mu_p={task.base_mu_p} px=({task.phase_x},{task.phase_y})",
            )

    detail_rows.sort(
        key=lambda row: (
            int(row["char_height_px"]),
            int(row["base_mu_p"]),
            float(row["rho"]),
            str(row["condition"]),
            int(row["phase_x"]),
            int(row["phase_y"]),
            int(row["noise_repeat"]),
        )
    )
    aggregate_rows = aggregate_condition_rows(detail_rows)
    advantage_rows = build_advantage_rows(aggregate_rows)
    paired_rows = build_paired_statistics(detail_rows)

    write_results_csv(config.output_dir / "detail_results.csv", detail_rows)
    write_results_csv(config.output_dir / "aggregate_by_condition.csv", aggregate_rows)
    write_results_csv(config.output_dir / "advantage_summary.csv", advantage_rows)
    write_results_csv(config.output_dir / "paired_statistics.csv", paired_rows)
    write_best_advantage_table(advantage_rows, config.output_dir / "best_advantage_table.csv")
    plot_advantage_heatmap(advantage_rows, config.output_dir / "advantage_heatmap.png")
    plot_selected_mu_curves(aggregate_rows, config.output_dir / "selected_mu_comparison.png")
    plot_paired_metric_heatmap(
        paired_rows,
        metric_key="paired_cov_char_acc",
        title="Paired covariance of char-accuracy",
        colorbar_label="cov(char_acc)",
        output_path=config.output_dir / "paired_cov_heatmap.png",
    )
    plot_paired_metric_heatmap(
        paired_rows,
        metric_key="paired_corr_char_acc",
        title="Paired correlation of char-accuracy",
        colorbar_label="corr(char_acc)",
        output_path=config.output_dir / "paired_corr_heatmap.png",
    )
    write_summary_md(
        config.output_dir / "SUMMARY.md",
        text=text,
        mu_values=config.mu_p_values,
        rho_values=config.rho_values,
        advantage_rows=advantage_rows,
        paired_rows=paired_rows,
    )

    best = max(advantage_rows, key=lambda row: float(row["char_acc_advantage"]))
    print(
        "Finished. Best coupled-over-control advantage: "
        f"mu_p={int(best['base_mu_p'])}, rho={float(best['rho']):.1f}, "
        f"delta={float(best['char_acc_advantage']):.6f}"
    )
    print(f"Outputs written to: {config.output_dir.resolve()}")


if __name__ == "__main__":
    main()

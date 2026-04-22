from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image

from mtfsnr_sim.analysis import (
    aggregate_condition_rows,
    plot_best_rho_heatmap,
    plot_huge_sample_score_scatter,
    plot_mtf_vs_score,
    plot_score_vs_rho,
    write_live_html_dashboard,
    write_best_tables,
    write_results_csv,
)
from mtfsnr_sim.chart_generator import (
    apply_integer_shift,
    build_phase_offsets,
    generate_permutation_strings,
    render_text_image,
)
from mtfsnr_sim.config import build_config
from mtfsnr_sim.evaluator import EvalTask, evaluate_task
from mtfsnr_sim.sensor_model import simulate_capture


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

    def update_many(self, increment: int, context: str) -> bool:
        self.completed += increment
        now = time.perf_counter()
        ratio = self.completed / self.total
        should_report = ratio >= self.next_report_ratio or self.completed >= self.total or (now - self.last_report_at) >= 15.0
        if not should_report:
            return False

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
        return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OCR-oriented aperture ratio simulation.")
    parser.add_argument(
        "--preset",
        default="smoke",
        choices=("smoke", "starter", "baseline", "full"),
        help="Parameter preset. Defaults to a fast smoke run.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output root. Defaults to outputs/<preset>.",
    )
    parser.add_argument(
        "--phase-count",
        type=int,
        default=None,
        help="Override the preset phase count.",
    )
    parser.add_argument(
        "--samples-per-condition",
        type=int,
        default=None,
        help="Override the number of random strings per character height.",
    )
    parser.add_argument(
        "--noise-repeats",
        type=int,
        default=None,
        help="Override the number of repeated noise draws for each rendered chart.",
    )
    parser.add_argument(
        "--font-limit",
        type=int,
        default=None,
        help="Keep only the first N fonts in the configured list.",
    )
    parser.add_argument(
        "--mu-p",
        type=int,
        nargs="*",
        default=None,
        help="Override photon budget grid, e.g. --mu-p 8 32 128 512.",
    )
    parser.add_argument(
        "--char-heights",
        type=int,
        nargs="*",
        default=None,
        help="Override character-height grid in pixels.",
    )
    parser.add_argument(
        "--rhos",
        type=float,
        nargs="*",
        default=None,
        help="Override aperture-ratio grid, e.g. --rhos 0.1 0.2 ... 1.0.",
    )
    parser.add_argument(
        "--whitelist",
        default=None,
        help="Override OCR whitelist and rendered alphabet, e.g. 0123456789.",
    )
    parser.add_argument(
        "--tesseract-path",
        default=None,
        help="Optional explicit Tesseract path.",
    )
    parser.add_argument(
        "--ideal-snr",
        action="store_true",
        help="Disable shot noise and read noise so only deterministic blur remains.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Process count for OCR workers. Defaults to a CPU-based heuristic.",
    )
    parser.add_argument(
        "--chart-preview-budget",
        type=int,
        default=8,
        help="How many ideal chart preview images to save.",
    )
    parser.add_argument(
        "--sensor-preview-budget",
        type=int,
        default=8,
        help="How many degraded sensor preview images to save.",
    )
    return parser.parse_args()


def _save_preview(path: Path, image_u8: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image_u8, mode="L").save(path)


def _float_scene_to_u8(scene: np.ndarray) -> np.ndarray:
    return np.rint(np.clip(scene, 0.0, 1.0) * 255.0).astype(np.uint8)


def _sensor_preview_specs(
    tasks: list[EvalTask],
    budget: int,
) -> list[tuple[EvalTask, int, float]]:
    specs: list[tuple[EvalTask, int, float]] = []
    for task in tasks:
        for mu_p in task.mu_p_values:
            for rho in task.rho_values:
                if len(specs) >= budget:
                    return specs
                specs.append((task, mu_p, rho))
    return specs


def _generate_sensor_previews(
    specs: list[tuple[EvalTask, int, float]],
    output_dir: Path,
) -> None:
    for preview_index, (task, mu_p, rho) in enumerate(specs, start=1):
        rng = np.random.default_rng(task.random_seed + task.task_index * 97 + preview_index)
        base_scene = render_text_image(
            text=task.text,
            font_path=task.font_path,
            char_height_px=task.char_height_px,
            oversample=task.oversample,
            padding_px=task.padding_px,
        )
        shifted_scene = apply_integer_shift(base_scene, task.phase_x, task.phase_y)
        capture = simulate_capture(
            scene_hr=shifted_scene,
            rho=rho,
            mu_p=mu_p,
            eta_si=task.eta_si,
            read_noise_e=task.read_noise_e,
            oversample=task.oversample,
            optical_sigma_hr=task.optical_sigma_hr,
            quant_bits=task.quant_bits,
            ocr_upscale=task.ocr_upscale,
            rng=rng,
            ideal_snr=task.ideal_snr,
        )
        preview_name = (
            f"h{task.char_height_px}_mu{mu_p}_rho{int(rho * 100):02d}_"
            f"{task.font_path.stem}_{task.text}_px{task.phase_x}_py{task.phase_y}.png"
        )
        _save_preview(output_dir / "sensor_previews" / preview_name, capture.ocr_ready_image_u8)


def _default_worker_count() -> int:
    cpu_count = os.cpu_count() or 1
    return max(1, cpu_count)


def main() -> None:
    args = _parse_args()
    config = build_config(args.preset, args.output_dir)
    if args.phase_count is not None:
        config.phase_count = args.phase_count
    if args.samples_per_condition is not None:
        config.samples_per_condition = args.samples_per_condition
    if args.noise_repeats is not None:
        config.noise_repeats = args.noise_repeats
    if args.font_limit is not None:
        config.fonts = config.fonts[: args.font_limit]
    if args.mu_p:
        config.mu_p_values = tuple(args.mu_p)
    if args.char_heights:
        config.char_heights_px = tuple(args.char_heights)
    if args.rhos:
        config.rho_values = tuple(args.rhos)
    if args.whitelist is not None:
        config.whitelist = args.whitelist
    if args.tesseract_path:
        config.tesseract_path = Path(args.tesseract_path)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(config.random_seed)
    phase_offsets = build_phase_offsets(config.oversample, config.phase_count)
    workers = args.workers or _default_worker_count()

    tasks: list[EvalTask] = []
    chart_preview_count = 0
    task_index = 0
    texts = generate_permutation_strings(
        rng=rng,
        count=config.samples_per_condition,
        alphabet=config.whitelist,
    )
    for char_height_px in config.char_heights_px:
        for font_path in config.fonts:
            for text in texts:
                if chart_preview_count < args.chart_preview_budget:
                    base_scene = render_text_image(
                        text=text,
                        font_path=font_path,
                        char_height_px=char_height_px,
                        oversample=config.oversample,
                        padding_px=config.padding_px,
                    )
                    chart_name = f"h{char_height_px}_{font_path.stem}_{text}.png"
                    _save_preview(
                        config.output_dir / "chart_previews" / chart_name,
                        _float_scene_to_u8(base_scene),
                    )
                    chart_preview_count += 1

                for phase_x in phase_offsets:
                    for phase_y in phase_offsets:
                        for mu_p in config.mu_p_values:
                            tasks.append(
                                EvalTask(
                                    task_index=task_index,
                                    char_height_px=char_height_px,
                                    font_path=font_path,
                                    text=text,
                                    phase_x=phase_x,
                                    phase_y=phase_y,
                                    mu_p_values=(mu_p,),
                                    rho_values=config.rho_values,
                                    noise_repeats=config.noise_repeats,
                                    oversample=config.oversample,
                                    padding_px=config.padding_px,
                                    eta_si=config.eta_si,
                                    read_noise_e=config.read_noise_e,
                                    optical_sigma_hr=config.optical_sigma_hr,
                                    quant_bits=config.quant_bits,
                                    ocr_upscale=config.ocr_upscale,
                                    ideal_snr=args.ideal_snr,
                                    tesseract_path=config.tesseract_path,
                                    whitelist=config.whitelist,
                                    psm=config.psm,
                                    random_seed=config.random_seed,
                                    point_preview_dir=config.output_dir / "point_previews",
                                )
                            )
                            task_index += 1

    evaluations_per_task = len(config.rho_values) * config.noise_repeats
    total_conditions = len(tasks) * evaluations_per_task
    print(
        f"Running {total_conditions} OCR evaluations with preset={args.preset} "
        f"using {workers} worker(s)."
    )
    progress = ProgressTracker(total_conditions)

    detail_rows: list[dict[str, object]] = []
    if workers == 1:
        for task in tasks:
            rows = evaluate_task(task)
            detail_rows.extend(rows)
            reported = progress.update_many(
                len(rows),
                f"h={task.char_height_px}px mu_p={task.mu_p_values[0]} "
                f"px=({task.phase_x},{task.phase_y}) text={task.text}",
            )
            if reported:
                partial_aggregate = aggregate_condition_rows(detail_rows)
                write_live_html_dashboard(
                    detail_rows=detail_rows,
                    aggregate_rows=partial_aggregate,
                    output_path=config.output_dir / "live_dashboard.html",
                )
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_to_task = {executor.submit(evaluate_task, task): task for task in tasks}
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                rows = future.result()
                detail_rows.extend(rows)
                reported = progress.update_many(
                    len(rows),
                    f"h={task.char_height_px}px mu_p={task.mu_p_values[0]} "
                    f"px=({task.phase_x},{task.phase_y}) text={task.text}",
                )
                if reported:
                    partial_aggregate = aggregate_condition_rows(detail_rows)
                    write_live_html_dashboard(
                        detail_rows=detail_rows,
                        aggregate_rows=partial_aggregate,
                        output_path=config.output_dir / "live_dashboard.html",
                    )

    detail_rows.sort(
        key=lambda row: (
            int(row["char_height_px"]),
            str(row["text"]),
            int(row["phase_x"]),
            int(row["phase_y"]),
            int(row["mu_p"]),
            float(row["rho"]),
            int(row.get("noise_repeat", 0)),
        )
    )

    sensor_specs = _sensor_preview_specs(tasks, args.sensor_preview_budget)
    _generate_sensor_previews(sensor_specs, config.output_dir)

    aggregate_rows = aggregate_condition_rows(detail_rows)

    write_results_csv(config.output_dir / "detail_results.csv", detail_rows)
    write_results_csv(config.output_dir / "aggregate_results.csv", aggregate_rows)
    write_best_tables(aggregate_rows, config.output_dir)
    write_live_html_dashboard(detail_rows, aggregate_rows, config.output_dir / "live_dashboard.html")
    plot_score_vs_rho(aggregate_rows, config.output_dir / "char_acc_vs_rho.png")
    plot_best_rho_heatmap(aggregate_rows, config.output_dir / "best_rho_heatmap.png")
    plot_mtf_vs_score(aggregate_rows, config.output_dir / "mtf_vs_char_acc.png")
    plot_huge_sample_score_scatter(detail_rows, config.output_dir / "huge_sample_score_scatter.png")

    best_overall = max(
        aggregate_rows,
        key=lambda item: (float(item["mean_char_acc"]), -float(item["mean_cer"]), -float(item["rho"])),
    )
    print(
        "Finished. "
        f"Best aggregate condition: rho={best_overall['rho']}, "
        f"mu_p={best_overall['mu_p']}, "
        f"h={best_overall['char_height_px']}px, "
        f"mean_char_acc={best_overall['mean_char_acc']:.3f}"
    )
    print(f"Outputs written to: {config.output_dir.resolve()}")


if __name__ == "__main__":
    main()

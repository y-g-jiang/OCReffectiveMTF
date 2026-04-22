from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from .chart_generator import apply_integer_shift, render_text_image
from .ocr_runner import run_tesseract
from .sensor_model import simulate_capture


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
class EvalTask:
    task_index: int
    char_height_px: int
    font_path: Path
    text: str
    phase_x: int
    phase_y: int
    mu_p_values: tuple[int, ...]
    rho_values: tuple[float, ...]
    noise_repeats: int
    oversample: int
    padding_px: int
    eta_si: float
    read_noise_e: float
    optical_sigma_hr: float
    quant_bits: int
    ocr_upscale: int
    ideal_snr: bool
    tesseract_path: Path
    whitelist: str
    psm: int
    random_seed: int
    point_preview_dir: Path | None = None


def _point_preview_filename(task_index: int, mu_p: int, rho: float, noise_repeat: int) -> str:
    rho_pct = int(round(rho * 100))
    return f"task{task_index:06d}_mu{mu_p:06d}_rho{rho_pct:03d}_n{noise_repeat}.png"


def _save_point_preview(image_u8: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image_u8, mode="L").save(output_path)


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


def evaluate_task(task: EvalTask) -> list[dict[str, object]]:
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
    for mu_p in task.mu_p_values:
        for rho in task.rho_values:
            for noise_repeat in range(task.noise_repeats):
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
                ocr = run_tesseract(
                    image_u8=capture.ocr_ready_image_u8,
                    tesseract_path=task.tesseract_path,
                    whitelist=task.whitelist,
                    psm=task.psm,
                )
                err = _cer(task.text, ocr.text)
                preview_relpath = ""
                if task.point_preview_dir is not None:
                    preview_name = _point_preview_filename(task.task_index, mu_p, rho, noise_repeat)
                    preview_path = task.point_preview_dir / preview_name
                    _save_point_preview(capture.ocr_ready_image_u8, preview_path)
                    preview_relpath = (Path(task.point_preview_dir.name) / preview_name).as_posix()
                rows.append(
                    {
                        "rho": rho,
                        "mu_p": mu_p,
                        "char_height_px": task.char_height_px,
                        "font_name": task.font_path.name,
                        "text": task.text,
                        "phase_x": task.phase_x,
                        "phase_y": task.phase_y,
                        "noise_repeat": noise_repeat,
                        "qe_total": round(capture.qe_total, 6),
                        "aperture_width_px": round(capture.aperture_width_px, 6),
                        "mtf_nyquist": round(capture.mtf_nyquist, 6),
                        "aperture_f50_cpp": round(capture.aperture_f50_cpp, 6),
                        "ocr_text": ocr.text,
                        "cer": round(err, 6),
                        "char_acc": round(1.0 - err, 6),
                        "preview_relpath": preview_relpath,
                    }
                )
    return rows

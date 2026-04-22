from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, uniform_filter


@dataclass(slots=True)
class SensorCapture:
    sensor_image_u8: np.ndarray
    ocr_ready_image_u8: np.ndarray
    qe_total: float
    aperture_width_px: float
    mtf_nyquist: float
    aperture_f50_cpp: float


def _normalized_sinc(x: float) -> float:
    if abs(x) < 1e-12:
        return 1.0
    return math.sin(math.pi * x) / (math.pi * x)


def theoretical_metrics(rho: float) -> tuple[float, float]:
    mtf_nyquist = abs(_normalized_sinc(0.5 * math.sqrt(rho)))
    aperture_f50_cpp = 0.603354564401614 / math.sqrt(rho)
    return mtf_nyquist, aperture_f50_cpp


def simulate_capture(
    scene_hr: np.ndarray,
    rho: float,
    mu_p: int,
    eta_si: float,
    read_noise_e: float,
    oversample: int,
    optical_sigma_hr: float,
    quant_bits: int,
    ocr_upscale: int,
    rng: np.random.Generator,
    ideal_snr: bool = False,
) -> SensorCapture:
    working = scene_hr.astype(np.float32, copy=True)
    if optical_sigma_hr > 0:
        working = gaussian_filter(working, sigma=optical_sigma_hr, mode="constant", cval=1.0)

    aperture_width_px = math.sqrt(rho) * oversample
    kernel_size = max(1, int(round(aperture_width_px)))
    blurred = uniform_filter(working, size=kernel_size, mode="constant", cval=1.0)

    sample_start = oversample // 2
    lowres = blurred[sample_start::oversample, sample_start::oversample]

    qe_total = eta_si * rho
    mean_electrons = np.clip(lowres * qe_total * mu_p, 0.0, None)
    if ideal_snr:
        electrons = mean_electrons.astype(np.float32, copy=False)
    else:
        shot = rng.poisson(mean_electrons).astype(np.float32)
        if read_noise_e > 0:
            shot += rng.normal(0.0, read_noise_e, size=shot.shape).astype(np.float32)
        electrons = np.clip(shot, 0.0, None)

    full_scale = max(qe_total * mu_p, 1e-6)
    normalized = np.clip(electrons / full_scale, 0.0, 1.0)

    max_dn = (1 << quant_bits) - 1
    sensor_u8 = np.rint(normalized * max_dn).astype(np.uint8)

    ocr_image = Image.fromarray(sensor_u8, mode="L")
    if ocr_upscale > 1:
        ocr_image = ocr_image.resize(
            (ocr_image.width * ocr_upscale, ocr_image.height * ocr_upscale),
            resample=Image.Resampling.BICUBIC,
        )

    mtf_nyquist, aperture_f50_cpp = theoretical_metrics(rho)
    return SensorCapture(
        sensor_image_u8=sensor_u8,
        ocr_ready_image_u8=np.asarray(ocr_image, dtype=np.uint8),
        qe_total=qe_total,
        aperture_width_px=aperture_width_px,
        mtf_nyquist=mtf_nyquist,
        aperture_f50_cpp=aperture_f50_cpp,
    )

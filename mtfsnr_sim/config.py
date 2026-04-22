from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _plate_font() -> tuple[Path, ...]:
    repo_root = Path(__file__).resolve().parents[1]
    bundled = repo_root / "assets" / "fonts" / "license_plate_bahnschrift.ttf"
    if bundled.exists():
        return (bundled,)

    fallback = Path(r"C:\Windows\Fonts\bahnschrift.ttf")
    if fallback.exists():
        return (fallback,)

    raise FileNotFoundError("Plate-style font not found. Expected assets/fonts/license_plate_bahnschrift.ttf.")


@dataclass(slots=True)
class ExperimentConfig:
    eta_si: float
    read_noise_e: float
    oversample: int
    rho_values: tuple[float, ...]
    mu_p_values: tuple[int, ...]
    char_heights_px: tuple[int, ...]
    phase_count: int
    samples_per_condition: int
    noise_repeats: int
    string_length: int
    fonts: tuple[Path, ...]
    padding_px: int
    optical_sigma_hr: float
    ocr_upscale: int
    quant_bits: int
    random_seed: int
    tesseract_path: Path
    output_dir: Path
    whitelist: str
    psm: int


def build_config(preset: str, output_dir: str | Path | None = None) -> ExperimentConfig:
    base = {
        "eta_si": 0.85,
        "read_noise_e": 1.0,
        "oversample": 16,
        "rho_values": tuple(i / 10 for i in range(1, 11)),
        "phase_count": 5,
        "samples_per_condition": 1,
        "noise_repeats": 2,
        "string_length": 26,
        "fonts": _plate_font(),
        "padding_px": 4,
        "optical_sigma_hr": 0.0,
        "ocr_upscale": 8,
        "quant_bits": 8,
        "random_seed": 1234,
        "tesseract_path": Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        "output_dir": Path(output_dir or "outputs") / preset,
        "whitelist": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "psm": 7,
    }

    if preset == "smoke":
        base["mu_p_values"] = (16, 128, 2048)
        base["char_heights_px"] = (6, 12)
        base["phase_count"] = 2
        base["noise_repeats"] = 1
    elif preset == "starter":
        base["mu_p_values"] = (8, 32, 128, 512, 2048, 8192)
        base["char_heights_px"] = (4, 6, 8, 10, 12, 16)
        base["noise_repeats"] = 1
    elif preset == "baseline":
        base["mu_p_values"] = (4, 16, 64, 256, 1024, 4096, 16384, 65536)
        base["char_heights_px"] = (4, 6, 8, 10, 12, 16, 20)
    elif preset == "full":
        base["mu_p_values"] = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536)
        base["char_heights_px"] = (3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 20, 24, 28, 32)
        base["noise_repeats"] = 3
    else:
        raise ValueError(f"Unknown preset: {preset}")

    return ExperimentConfig(**base)

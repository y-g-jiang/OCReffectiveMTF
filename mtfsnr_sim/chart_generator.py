from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def generate_random_strings(
    rng: np.random.Generator,
    length: int,
    count: int,
    alphabet: str = ALPHABET,
) -> list[str]:
    samples = []
    letters = np.array(list(alphabet))
    for _ in range(count):
        choice = rng.choice(letters, size=length, replace=True)
        samples.append("".join(choice.tolist()))
    return samples


def generate_permutation_strings(
    rng: np.random.Generator,
    count: int,
    alphabet: str = ALPHABET,
) -> list[str]:
    letters = np.array(list(alphabet))
    samples = []
    for _ in range(count):
        perm = rng.permutation(letters)
        samples.append("".join(perm.tolist()))
    return samples


def build_phase_offsets(oversample: int, phase_count: int) -> tuple[int, ...]:
    if phase_count <= 1:
        return (0,)
    offsets = np.linspace(0, oversample - 1, phase_count, dtype=int)
    return tuple(int(v) for v in offsets)


def _measure_text_bbox(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int, int, int]:
    canvas = Image.new("L", (2048, 1024), 255)
    draw = ImageDraw.Draw(canvas)
    return draw.textbbox((0, 0), text, font=font)


def _find_font_size(font_path: Path, text: str, target_height_hr: int) -> ImageFont.FreeTypeFont:
    low = 4
    high = max(16, target_height_hr * 3)
    best_font = ImageFont.truetype(str(font_path), size=low)
    best_error = float("inf")

    while low <= high:
        mid = (low + high) // 2
        font = ImageFont.truetype(str(font_path), size=mid)
        bbox = _measure_text_bbox(font, text)
        height = max(1, bbox[3] - bbox[1])
        error = abs(height - target_height_hr)
        if error < best_error:
            best_error = error
            best_font = font
        if height < target_height_hr:
            low = mid + 1
        elif height > target_height_hr:
            high = mid - 1
        else:
            return font

    return best_font


def render_text_image(
    text: str,
    font_path: Path,
    char_height_px: int,
    oversample: int,
    padding_px: int,
) -> np.ndarray:
    target_height_hr = char_height_px * oversample
    font = _find_font_size(font_path, text, target_height_hr)
    bbox = _measure_text_bbox(font, text)
    pad_hr = padding_px * oversample
    width = (bbox[2] - bbox[0]) + pad_hr * 2
    height = (bbox[3] - bbox[1]) + pad_hr * 2

    width = ((width + oversample - 1) // oversample) * oversample
    height = ((height + oversample - 1) // oversample) * oversample

    canvas = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(canvas)
    x = pad_hr - bbox[0]
    y = pad_hr - bbox[1]
    draw.text((x, y), text, font=font, fill=0)

    image = np.asarray(canvas, dtype=np.float32) / 255.0
    return image


def apply_integer_shift(image: np.ndarray, shift_x: int, shift_y: int, fill_value: float = 1.0) -> np.ndarray:
    if shift_x == 0 and shift_y == 0:
        return image.copy()

    shifted = np.full_like(image, fill_value)

    src_y0 = max(0, -shift_y)
    src_y1 = image.shape[0] - max(0, shift_y)
    dst_y0 = max(0, shift_y)
    dst_y1 = dst_y0 + max(0, src_y1 - src_y0)

    src_x0 = max(0, -shift_x)
    src_x1 = image.shape[1] - max(0, shift_x)
    dst_x0 = max(0, shift_x)
    dst_x1 = dst_x0 + max(0, src_x1 - src_x0)

    if src_x1 > src_x0 and src_y1 > src_y0:
        shifted[dst_y0:dst_y1, dst_x0:dst_x1] = image[src_y0:src_y1, src_x0:src_x1]
    return shifted

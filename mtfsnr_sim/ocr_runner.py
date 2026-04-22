from __future__ import annotations

import atexit
import itertools
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


_TEMP_DIR: Path | None = None
_TEMP_COUNTER = itertools.count()


def _worker_temp_dir() -> Path:
    global _TEMP_DIR
    if _TEMP_DIR is None:
        _TEMP_DIR = Path(tempfile.mkdtemp(prefix="mtfsnr_worker_"))
        atexit.register(lambda: shutil.rmtree(_TEMP_DIR, ignore_errors=True))
    return _TEMP_DIR


@dataclass(slots=True)
class OCRResult:
    text: str
    raw_text: str


def run_tesseract(
    image_u8: np.ndarray,
    tesseract_path: Path,
    whitelist: str,
    psm: int,
) -> OCRResult:
    if not tesseract_path.exists():
        raise FileNotFoundError(f"Tesseract not found: {tesseract_path}")

    temp_dir = _worker_temp_dir()
    image_path = temp_dir / f"sample_{next(_TEMP_COUNTER)}.bmp"
    Image.fromarray(image_u8, mode="L").save(image_path)

    cmd = [
        str(tesseract_path),
        str(image_path),
        "stdout",
        "--psm",
        str(psm),
        "-c",
        f"tessedit_char_whitelist={whitelist}",
        "-c",
        "load_system_dawg=0",
        "-c",
        "load_freq_dawg=0",
    ]
    kwargs = {
        "check": False,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
    }
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        completed = subprocess.run(cmd, **kwargs)
    finally:
        image_path.unlink(missing_ok=True)

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(f"Tesseract failed with code {completed.returncode}: {stderr}")

    raw = completed.stdout
    clean = "".join(ch for ch in raw.upper() if ch in whitelist)
    return OCRResult(text=clean, raw_text=raw)

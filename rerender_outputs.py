from __future__ import annotations

import argparse
import csv
from pathlib import Path

from mtfsnr_sim.analysis import (
    plot_best_rho_heatmap,
    plot_huge_sample_score_scatter,
    plot_mtf_vs_score,
    plot_score_vs_rho,
    write_live_html_dashboard,
)


def _read_csv(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    parsed: list[dict[str, object]] = []
    for row in rows:
        parsed_row: dict[str, object] = dict(row)
        for key in ("rho", "mean_cer", "mean_char_acc", "qe_total", "mtf_nyquist", "aperture_f50_cpp", "cer", "char_acc"):
            if key in parsed_row and parsed_row[key] != "":
                parsed_row[key] = float(parsed_row[key])
        for key in ("mu_p", "char_height_px", "n_eval", "phase_x", "phase_y", "noise_repeat"):
            if key in parsed_row and parsed_row[key] != "":
                parsed_row[key] = int(float(parsed_row[key]))
        parsed.append(parsed_row)
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Rerender charts from existing CSV outputs.")
    parser.add_argument("output_dir", help="Existing experiment output directory containing CSV files.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    detail_rows = _read_csv(output_dir / "detail_results.csv")
    aggregate_rows = _read_csv(output_dir / "aggregate_results.csv")

    plot_score_vs_rho(aggregate_rows, output_dir / "char_acc_vs_rho.png")
    plot_best_rho_heatmap(aggregate_rows, output_dir / "best_rho_heatmap.png")
    plot_mtf_vs_score(aggregate_rows, output_dir / "mtf_vs_char_acc.png")
    plot_huge_sample_score_scatter(detail_rows, output_dir / "huge_sample_score_scatter.png")
    write_live_html_dashboard(detail_rows, aggregate_rows, output_dir / "live_dashboard.html")
    print(f"Rerendered charts under: {output_dir}")


if __name__ == "__main__":
    main()

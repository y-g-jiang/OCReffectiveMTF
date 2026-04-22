from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib import colors as mcolors


def cer(reference: str, hypothesis: str) -> float:
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


def write_results_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_metric_table(
    aggregate_rows: list[dict[str, object]],
    metric_key: str,
    output_path: Path,
    best_of_rho: bool = False,
) -> None:
    if not aggregate_rows:
        return

    mu_values = sorted({int(row["mu_p"]) for row in aggregate_rows})
    heights = sorted({int(row["char_height_px"]) for row in aggregate_rows})
    rows_out: list[dict[str, object]] = []

    for height in heights:
        row_out: dict[str, object] = {"char_height_px": height}
        for mu_p in mu_values:
            subset = [
                row
                for row in aggregate_rows
                if int(row["char_height_px"]) == height and int(row["mu_p"]) == mu_p
            ]
            if not subset:
                row_out[str(mu_p)] = ""
                continue
            if best_of_rho:
                best = max(subset, key=lambda item: (float(item["mean_char_acc"]), -float(item["rho"])))
                row_out[str(mu_p)] = best[metric_key]
            else:
                subset.sort(key=lambda item: float(item["rho"]))
                row_out[str(mu_p)] = subset[0][metric_key]
        rows_out.append(row_out)

    write_results_csv(output_path, rows_out)


def aggregate_condition_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[float, int, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = (float(row["rho"]), int(row["mu_p"]), int(row["char_height_px"]))
        grouped[key].append(row)

    aggregates = []
    for (rho, mu_p, char_height_px), items in sorted(grouped.items()):
        cer_values = np.array([float(item["cer"]) for item in items], dtype=float)
        char_acc_values = np.array([float(item["char_acc"]) for item in items], dtype=float)
        aggregates.append(
            {
                "rho": rho,
                "mu_p": mu_p,
                "char_height_px": char_height_px,
                "mean_cer": float(cer_values.mean()),
                "mean_char_acc": float(char_acc_values.mean()),
                "n_eval": len(items),
                "qe_total": float(items[0]["qe_total"]),
                "mtf_nyquist": float(items[0]["mtf_nyquist"]),
                "aperture_f50_cpp": float(items[0]["aperture_f50_cpp"]),
            }
        )
    return aggregates


def _group_by_height(aggregate_rows: list[dict[str, object]]) -> dict[int, list[dict[str, object]]]:
    grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in aggregate_rows:
        grouped[int(row["char_height_px"])].append(row)
    return grouped


_PLOT_STYLE_READY = False


def _configure_plot_style() -> None:
    global _PLOT_STYLE_READY
    if _PLOT_STYLE_READY:
        return

    candidate_fonts = (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    )
    for font_path in candidate_fonts:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
            family_name = font_manager.FontProperties(fname=str(font_path)).get_name()
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [family_name]
            break

    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.facecolor"] = "white"
    plt.rcParams["savefig.facecolor"] = "white"
    _PLOT_STYLE_READY = True


def _add_axes_watermark(ax: plt.Axes, text: str = "y-g-jiang.github.io") -> None:
    ax.text(
        0.5,
        0.5,
        text,
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=28,
        color="#7d8794",
        alpha=0.16,
        rotation=28,
        zorder=0,
    )


def plot_score_vs_rho(aggregate_rows: list[dict[str, object]], output_path: Path) -> None:
    if not aggregate_rows:
        return

    _configure_plot_style()
    grouped = _group_by_height(aggregate_rows)
    heights = sorted(grouped.keys())
    fig, axes = plt.subplots(len(heights), 1, figsize=(9, 3.5 * len(heights)), squeeze=False)
    fig.patch.set_facecolor("white")

    for ax, height in zip(axes.flat, heights):
        rows = grouped[height]
        mu_values = sorted({int(row["mu_p"]) for row in rows})
        _add_axes_watermark(ax)
        for mu_p in mu_values:
            subset = [row for row in rows if int(row["mu_p"]) == mu_p]
            subset.sort(key=lambda item: float(item["rho"]))
            ax.plot(
                [float(item["rho"]) for item in subset],
                [float(item["mean_char_acc"]) for item in subset],
                marker="o",
                label=f"光子数={mu_p}",
            )
        ax.set_title(f"字符正确率-填充率曲线（字号={height}px）")
        ax.set_xlabel("填充率 rho")
        ax.set_ylabel("平均字符正确率")
        ax.set_ylim(-0.02, 1.02)
        ax.grid(True, alpha=0.3)
        ax.legend(ncols=3, fontsize=8)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def plot_best_rho_heatmap(aggregate_rows: list[dict[str, object]], output_path: Path) -> None:
    if not aggregate_rows:
        return

    _configure_plot_style()
    mu_values = sorted({int(row["mu_p"]) for row in aggregate_rows})
    heights = sorted({int(row["char_height_px"]) for row in aggregate_rows})
    grid = np.full((len(heights), len(mu_values)), np.nan, dtype=float)

    for h_idx, height in enumerate(heights):
        for m_idx, mu_p in enumerate(mu_values):
            subset = [
                row
                for row in aggregate_rows
                if int(row["char_height_px"]) == height and int(row["mu_p"]) == mu_p
            ]
            if not subset:
                continue
            best = max(subset, key=lambda item: (float(item["mean_char_acc"]), -float(item["rho"])))
            grid[h_idx, m_idx] = float(best["rho"])

    fig, ax = plt.subplots(figsize=(1.8 * len(mu_values), 1.2 * len(heights) + 2))
    fig.patch.set_facecolor("white")
    im = ax.imshow(grid, cmap="viridis", aspect="auto", vmin=0.1, vmax=1.0)
    _add_axes_watermark(ax, text="y-g-jiang.github.io")
    ax.set_xticks(np.arange(len(mu_values)), labels=[str(v) for v in mu_values])
    ax.set_yticks(np.arange(len(heights)), labels=[str(v) for v in heights])
    ax.set_xlabel("入射光子数 mu_p")
    ax.set_ylabel("字符高度（px）")
    ax.set_title("最优填充率热图")

    for h_idx, height in enumerate(heights):
        for m_idx, mu_p in enumerate(mu_values):
            if np.isnan(grid[h_idx, m_idx]):
                continue
            ax.text(m_idx, h_idx, f"{grid[h_idx, m_idx]:.1f}", ha="center", va="center", color="white")

    fig.colorbar(im, ax=ax, label="最优 rho")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def plot_mtf_vs_score(aggregate_rows: list[dict[str, object]], output_path: Path) -> None:
    if not aggregate_rows:
        return

    _configure_plot_style()
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("white")
    mu_values = sorted({int(row["mu_p"]) for row in aggregate_rows})
    cmap = plt.get_cmap("plasma", len(mu_values))
    _add_axes_watermark(ax)

    for index, mu_p in enumerate(mu_values):
        subset = [row for row in aggregate_rows if int(row["mu_p"]) == mu_p]
        ax.scatter(
            [float(item["aperture_f50_cpp"]) for item in subset],
            [float(item["mean_char_acc"]) for item in subset],
            label=f"光子数={mu_p}",
            alpha=0.75,
            color=cmap(index),
        )

    ax.set_title("理论像素 MTF50 与 OCR 字符正确率")
    ax.set_xlabel("理论 aperture MTF50（cycles/pixel）")
    ax.set_ylabel("平均字符正确率")
    ax.set_ylim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    ax.legend(ncols=3, fontsize=8)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def write_best_tables(aggregate_rows: list[dict[str, object]], output_dir: Path) -> None:
    write_metric_table(
        aggregate_rows=aggregate_rows,
        metric_key="rho",
        output_path=output_dir / "best_rho_table.csv",
        best_of_rho=True,
    )
    write_metric_table(
        aggregate_rows=aggregate_rows,
        metric_key="mean_char_acc",
        output_path=output_dir / "best_char_acc_table.csv",
        best_of_rho=True,
    )


def plot_huge_sample_score_scatter(detail_rows: list[dict[str, object]], output_path: Path) -> None:
    if not detail_rows:
        return

    _configure_plot_style()
    mu_values = sorted({int(row["mu_p"]) for row in detail_rows})
    heights = sorted({int(row["char_height_px"]) for row in detail_rows})
    mu_index = {mu_p: idx for idx, mu_p in enumerate(mu_values)}
    height_index = {height: idx for idx, height in enumerate(heights)}
    single_mu = len(mu_values) == 1

    if single_mu and len(heights) > 1:
        fig_width = max(16, 1.8 * len(heights) + 6)
        fig_height = 10
        fig, axes = plt.subplots(1, 1, figsize=(fig_width, fig_height), squeeze=False)
    else:
        fig_width = max(18, 1.6 * len(mu_values) + 6)
        fig_height = max(14, 3.0 * len(heights) + 2)
        fig, axes = plt.subplots(len(heights), 1, figsize=(fig_width, fig_height), squeeze=False)
    fig.patch.set_facecolor("white")
    cmap = plt.get_cmap("gray_r")
    norm = mcolors.Normalize(vmin=0.0, vmax=1.0)
    scatter_artist = None

    if single_mu and len(heights) > 1:
        ax = axes.flat[0]
        _add_axes_watermark(ax)
        xs = []
        ys = []
        colors = []
        for row in detail_rows:
            base_x = height_index[int(row["char_height_px"])]
            phase_x = int(row["phase_x"])
            phase_y = int(row["phase_y"])
            noise_repeat = int(row.get("noise_repeat", 0))
            jitter_x = ((phase_x + 1) * 0.013) + ((phase_y + 1) * 0.007) + (noise_repeat * 0.018)
            jitter_x = (jitter_x % 0.24) - 0.12
            jitter_y = ((phase_x * 0.009) - (phase_y * 0.007) + noise_repeat * 0.011) % 0.08
            jitter_y -= 0.04
            xs.append(base_x + jitter_x)
            ys.append(float(row["rho"]) + jitter_y)
            colors.append(float(row["char_acc"]))

        scatter_artist = ax.scatter(
            xs,
            ys,
            c=colors,
            cmap=cmap,
            norm=norm,
            s=18,
            alpha=1.0,
            edgecolors="none",
            rasterized=True,
        )
        ax.set_title(f"单图样本散点图（入射光子数={mu_values[0]}）")
        ax.set_ylabel("填充率 rho")
        ax.set_xlabel("字符高度 px")
        ax.set_ylim(0.04, 1.06)
        ax.set_yticks([i / 10 for i in range(1, 11)])
        ax.set_xticks(np.arange(len(heights)), labels=[str(v) for v in heights])
        ax.set_xlim(-0.5, len(heights) - 0.5)
        ax.grid(True, alpha=0.18)
    else:
        for ax, height in zip(axes.flat, heights):
            subset = [row for row in detail_rows if int(row["char_height_px"]) == height]
            if not subset:
                continue

            _add_axes_watermark(ax)
            xs = []
            ys = []
            colors = []
            for row in subset:
                base_x = mu_index[int(row["mu_p"])]
                phase_x = int(row["phase_x"])
                phase_y = int(row["phase_y"])
                noise_repeat = int(row.get("noise_repeat", 0))
                jitter_x = ((phase_x + 1) * 0.013) + ((phase_y + 1) * 0.007) + (noise_repeat * 0.018)
                jitter_x = (jitter_x % 0.24) - 0.12
                jitter_y = ((phase_x * 0.009) - (phase_y * 0.007) + noise_repeat * 0.011) % 0.08
                jitter_y -= 0.04
                xs.append(base_x + jitter_x)
                ys.append(float(row["rho"]) + jitter_y)
                colors.append(float(row["char_acc"]))

            scatter_artist = ax.scatter(
                xs,
                ys,
                c=colors,
                cmap=cmap,
                norm=norm,
                s=18,
                alpha=1.0,
                edgecolors="none",
                rasterized=True,
            )
            ax.set_title(f"单图样本散点图（字号={height}px）")
            ax.set_ylabel("填充率 rho")
            ax.set_ylim(0.04, 1.06)
            ax.set_yticks([i / 10 for i in range(1, 11)])
            ax.grid(True, alpha=0.18)

        for ax in axes.flat:
            ax.set_xticks(np.arange(len(mu_values)), labels=[str(v) for v in mu_values])
            ax.set_xlim(-0.5, len(mu_values) - 0.5)
            ax.set_xlabel("入射光子数 mu_p")

    if scatter_artist is not None:
        cbar = fig.colorbar(
            scatter_artist,
            ax=axes.ravel().tolist(),
            location="right",
            pad=0.035,
            fraction=0.03,
        )
        cbar.set_label("字符正确率")

    if single_mu and len(heights) > 1:
        fig.suptitle("超大单图样本散点图（横轴为字符高度）", fontsize=16, y=0.995)
    else:
        fig.suptitle("超大单图样本散点图", fontsize=16, y=0.995)
    fig.subplots_adjust(left=0.06, right=0.88, top=0.975, bottom=0.035, hspace=0.34)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def write_live_html_dashboard(
    detail_rows: list[dict[str, object]],
    aggregate_rows: list[dict[str, object]],
    output_path: Path,
) -> None:
    if not detail_rows:
        return

    mu_values = sorted({int(row["mu_p"]) for row in detail_rows})
    heights = sorted({int(row["char_height_px"]) for row in detail_rows})
    mu_index = {mu_p: idx for idx, mu_p in enumerate(mu_values)}
    height_index = {height: idx for idx, height in enumerate(heights)}
    band_height = 1.2
    single_height = len(heights) == 1
    single_mu = len(mu_values) == 1

    points = []
    for row in detail_rows:
        phase_x = int(row["phase_x"])
        phase_y = int(row["phase_y"])
        noise_repeat = int(row.get("noise_repeat", 0))
        if single_mu and not single_height:
            x = height_index[int(row["char_height_px"])]
            x += ((phase_x + 1) * 0.013 + (phase_y + 1) * 0.007 + noise_repeat * 0.018) % 0.24 - 0.12
        else:
            x = mu_index[int(row["mu_p"])]
            x += ((phase_x + 1) * 0.013 + (phase_y + 1) * 0.007 + noise_repeat * 0.018) % 0.24 - 0.12
        y = float(row["rho"])
        if single_height:
            y += ((phase_x * 0.009) - (phase_y * 0.007) + noise_repeat * 0.011) % 0.06 - 0.03
        elif single_mu:
            y += ((phase_x * 0.009) - (phase_y * 0.007) + noise_repeat * 0.011) % 0.08 - 0.04
        else:
            y = height_index[int(row["char_height_px"])] * band_height + y
            y += ((phase_x * 0.009) - (phase_y * 0.007) + noise_repeat * 0.011) % 0.08 - 0.04
        points.append(
            {
                "x": round(x, 6),
                "y": round(y, 6),
                "score": round(float(row["char_acc"]), 6),
                "cer": round(float(row["cer"]), 6),
                "mu_p": int(row["mu_p"]),
                "rho": float(row["rho"]),
                "char_height_px": int(row["char_height_px"]),
                "text": str(row["text"]),
                "ocr_text": str(row["ocr_text"]),
                "font_name": str(row.get("font_name", "")),
                "phase_x": phase_x,
                "phase_y": phase_y,
                "noise_repeat": noise_repeat,
                "previewRelPath": str(row.get("preview_relpath", "")),
            }
        )

    top_rows = sorted(
        aggregate_rows,
        key=lambda item: (float(item["mean_char_acc"]), -float(item["rho"])),
        reverse=True,
    )[:12]
    table_rows = []
    for row in top_rows:
        table_rows.append(
            "<tr>"
            f"<td>{int(row['char_height_px'])}</td>"
            f"<td>{int(row['mu_p'])}</td>"
            f"<td>{float(row['rho']):.1f}</td>"
            f"<td>{float(row['mean_char_acc']):.4f}</td>"
            f"<td>{int(row['n_eval'])}</td>"
            "</tr>"
        )

    payload = {
        "muValues": mu_values,
        "heights": heights,
        "bandHeight": band_height,
        "singleHeight": single_height,
        "singleMu": single_mu,
        "points": points,
    }
    updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>实时散点面板</title>
  <style>
    html {{
      height: 100%;
    }}
    body {{
      margin: 0;
      height: 100%;
      overflow: hidden;
      font-family: 'Microsoft YaHei', 'SimHei', Consolas, 'SFMono-Regular', monospace;
      background: #ffffff;
      color: #18212b;
    }}
    .wrap {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) clamp(300px, 24vw, 380px);
      gap: 18px;
      padding: 18px;
      box-sizing: border-box;
      height: 100vh;
    }}
    .panel {{
      background: #ffffff;
      border: 1px solid #d8dee6;
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 8px 24px rgba(37, 52, 70, 0.08);
      min-height: 0;
      overflow: hidden;
    }}
    .plot-panel {{
      display: flex;
      flex-direction: column;
      min-height: 0;
    }}
    .plot-host {{
      flex: 1 1 auto;
      min-height: 0;
    }}
    .side-panel {{
      overflow: auto;
    }}
    h1, h2 {{
      margin: 0 0 10px 0;
      font-weight: 700;
    }}
    .meta {{
      color: #5a6675;
      margin-bottom: 12px;
      font-size: 13px;
    }}
    canvas {{
      width: 100%;
      height: 100%;
      display: block;
      cursor: default;
      background: #ffffff;
      border-radius: 10px;
      border: 1px solid #e4e8ee;
    }}
    @media (max-width: 1180px) {{
      .wrap {{
        grid-template-columns: minmax(0, 1fr);
        grid-template-rows: minmax(0, 1fr) minmax(220px, 36vh);
      }}
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      text-align: right;
      padding: 6px 8px;
      border-bottom: 1px solid #e7ebf0;
    }}
    th:first-child, td:first-child {{
      text-align: left;
    }}
    .legend {{
      margin: 6px 0 14px 0;
      color: #5e6978;
      font-size: 12px;
    }}
    .legend-row {{
      display: grid;
      grid-template-columns: 28px 1fr 36px;
      gap: 10px;
      align-items: center;
      margin-bottom: 8px;
    }}
    .legend-bar {{
      height: 220px;
      width: 18px;
      border-radius: 999px;
      background: linear-gradient(180deg, #000000, #7f7f7f, #ffffff);
      border: 1px solid #d7dde6;
      justify-self: center;
    }}
    .legend-note {{
      line-height: 1.5;
    }}
    .hint {{
      margin-top: 12px;
      color: #5a6675;
      font-size: 12px;
      line-height: 1.6;
    }}
    .control-card {{
      margin: 14px 0 12px 0;
      padding: 12px 14px;
      border: 1px solid #e0e6ee;
      border-radius: 12px;
      background: #fafcff;
    }}
    .control-title {{
      margin-bottom: 8px;
      color: #223243;
      font-size: 13px;
      font-weight: 700;
    }}
    .control-row {{
      display: grid;
      grid-template-columns: 1fr 56px;
      gap: 12px;
      align-items: center;
    }}
    .control-actions {{
      margin-top: 10px;
      display: flex;
      justify-content: stretch;
    }}
    .control-button {{
      width: 100%;
      border: 1px solid #cfd8e3;
      background: #ffffff;
      color: #223243;
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }}
    .control-button:disabled {{
      opacity: 0.65;
      cursor: progress;
    }}
    .control-value {{
      text-align: right;
      color: #405060;
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }}
    input[type="range"] {{
      width: 100%;
      accent-color: #445261;
    }}
    .modal-backdrop {{
      position: fixed;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      background: rgba(18, 27, 38, 0.42);
      padding: 18px;
      z-index: 20;
    }}
    .modal-backdrop.hidden {{
      display: none;
    }}
    .modal-card {{
      width: min(1080px, calc(100vw - 36px));
      max-height: calc(100vh - 36px);
      overflow: auto;
      background: #ffffff;
      border-radius: 16px;
      border: 1px solid #d6dce4;
      box-shadow: 0 24px 60px rgba(17, 27, 39, 0.24);
      padding: 18px;
      position: relative;
    }}
    .modal-close {{
      position: absolute;
      top: 12px;
      right: 12px;
      width: 40px;
      height: 40px;
      border: none;
      border-radius: 999px;
      background: #eff3f7;
      color: #223243;
      font-size: 24px;
      cursor: pointer;
    }}
    .modal-grid {{
      display: grid;
      grid-template-columns: minmax(380px, 1fr) 320px;
      gap: 18px;
      align-items: start;
    }}
    .modal-image-wrap {{
      min-height: 260px;
      border-radius: 12px;
      border: 1px solid #d9e0e8;
      background: linear-gradient(180deg, #ffffff, #f6f8fb);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 14px;
    }}
    .modal-image-wrap img {{
      max-width: 100%;
      max-height: 62vh;
      image-rendering: pixelated;
      border: 1px solid #d8dee6;
      background: #ffffff;
    }}
    .modal-image-empty {{
      color: #677383;
      font-size: 14px;
      text-align: center;
      line-height: 1.7;
    }}
    .modal-meta {{
      display: grid;
      gap: 12px;
    }}
    .score-pill {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      width: fit-content;
      padding: 10px 14px;
      border-radius: 999px;
      background: #f5f8fb;
      border: 1px solid #dde4ec;
      font-size: 15px;
      font-weight: 700;
      color: #18212b;
    }}
    .score-dot {{
      width: 14px;
      height: 14px;
      border-radius: 999px;
      border: 1px solid rgba(0, 0, 0, 0.12);
    }}
    .meta-card {{
      border: 1px solid #dde4ec;
      border-radius: 12px;
      padding: 12px 14px;
      background: #fbfcfe;
    }}
    .meta-card-title {{
      margin-bottom: 10px;
      font-weight: 700;
      color: #223243;
    }}
    .meta-row {{
      display: grid;
      grid-template-columns: 104px 1fr;
      gap: 10px;
      font-size: 13px;
      line-height: 1.6;
      color: #445261;
      margin-bottom: 6px;
    }}
    .meta-row strong {{
      color: #14202c;
      word-break: break-all;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="panel plot-panel">
      <h1>实时样本散点图</h1>
      <div class="meta">更新时间 {escape(updated)} | 点数 {len(points)} | 每个点代表一张图的 OCR 得分</div>
      <div id="plotHost" class="plot-host">
        <canvas id="plot" width="2400" height="1800"></canvas>
      </div>
    </section>
    <aside class="panel side-panel">
      <h2>图例与较优结果</h2>
      <div class="meta">按已完成样本的平均字符正确率排序</div>
      <div class="legend">
        <div class="legend-row">
          <div>1.0</div>
          <div class="legend-bar"></div>
          <div></div>
        </div>
        <div class="legend-row">
          <div>0.0</div>
          <div class="legend-note">颜色亮度表示单张图的字符正确率。已增强低分段对比，`0.0` 与 `0.1` 的差别会更明显。</div>
          <div></div>
        </div>
      </div>
      <div class="control-card">
        <div class="control-title">散点大小</div>
        <div class="control-row">
          <input id="pointSizeRange" type="range" min="1" max="14" step="0.2" value="4.2">
          <div id="pointSizeValue" class="control-value">4.2</div>
        </div>
        <div class="control-actions">
          <button id="exportChartButton" class="control-button" type="button">导出当前大图</button>
        </div>
      </div>
      <table>
        <tbody>
          {''.join(table_rows)}
        </tbody>
      </table>
      <div class="hint">点击散点可查看该点对应的识别输入图、得分、识别结果和相位信息。</div>
    </aside>
  </div>
  <div id="modalBackdrop" class="modal-backdrop hidden">
    <div class="modal-card">
      <button id="modalClose" class="modal-close" type="button" aria-label="关闭">×</button>
      <div class="modal-grid">
        <div class="modal-image-wrap">
          <img id="modalImage" alt="识别图像预览" hidden>
          <div id="modalImageEmpty" class="modal-image-empty" hidden>当前结果目录里没有这一个点的预览图。</div>
        </div>
        <div class="modal-meta">
          <div class="score-pill">
            <span id="modalScoreDot" class="score-dot"></span>
            <span id="modalScoreText">字符正确率 0.0000</span>
          </div>
          <div class="meta-card">
            <div class="meta-card-title">样本信息</div>
            <div class="meta-row"><span>字符高度</span><strong id="modalCharHeight"></strong></div>
            <div class="meta-row"><span>入射光子</span><strong id="modalMuP"></strong></div>
            <div class="meta-row"><span>填充率</span><strong id="modalRho"></strong></div>
            <div class="meta-row"><span>相位</span><strong id="modalPhase"></strong></div>
            <div class="meta-row"><span>噪声重复</span><strong id="modalNoiseRepeat"></strong></div>
            <div class="meta-row"><span>字体</span><strong id="modalFontName"></strong></div>
          </div>
          <div class="meta-card">
            <div class="meta-card-title">识别结果</div>
            <div class="meta-row"><span>目标字符串</span><strong id="modalText"></strong></div>
            <div class="meta-row"><span>OCR 输出</span><strong id="modalOcrText"></strong></div>
            <div class="meta-row"><span>CER</span><strong id="modalCer"></strong></div>
            <div class="meta-row"><span>预览路径</span><strong id="modalPreviewPath"></strong></div>
          </div>
        </div>
      </div>
    </div>
  </div>
  <script>
    const payload = {json.dumps(payload, ensure_ascii=False)};
    const plotHost = document.getElementById('plotHost');
    const canvas = document.getElementById('plot');
    const ctx = canvas.getContext('2d');
    const modalBackdrop = document.getElementById('modalBackdrop');
    const modalClose = document.getElementById('modalClose');
    const modalImage = document.getElementById('modalImage');
    const modalImageEmpty = document.getElementById('modalImageEmpty');
    const pointSizeRange = document.getElementById('pointSizeRange');
    const pointSizeValue = document.getElementById('pointSizeValue');
    const exportChartButton = document.getElementById('exportChartButton');
    let width = 0;
    let height = 0;
    const pad = {{ left: 110, right: 40, top: 40, bottom: 80 }};
    let plotW = 0;
    let plotH = 0;
    const maxY = (payload.singleHeight || payload.singleMu) ? 1.05 : payload.heights.length * payload.bandHeight;
    const pointSizeStorageKey = 'mtfsnr.scatterPointRadius';
    let pointRadius = 4.2;

    function colorFor(score) {{
      const clipped = Math.max(0, Math.min(1, score));
      const value = Math.round((1 - clipped) * 255);
      return 'rgb(' + value + ', ' + value + ', ' + value + ')';
    }}

    function loadPointRadius() {{
      const raw = window.localStorage ? window.localStorage.getItem(pointSizeStorageKey) : null;
      const parsed = raw ? Number.parseFloat(raw) : Number.NaN;
      if (Number.isFinite(parsed)) {{
        pointRadius = Math.max(1, Math.min(14, parsed));
      }}
      pointSizeRange.value = pointRadius.toFixed(1);
      pointSizeValue.textContent = pointRadius.toFixed(1);
    }}

    function setPointRadius(value) {{
      pointRadius = Math.max(1, Math.min(14, value));
      pointSizeRange.value = pointRadius.toFixed(1);
      pointSizeValue.textContent = pointRadius.toFixed(1);
      if (window.localStorage) {{
        window.localStorage.setItem(pointSizeStorageKey, pointRadius.toFixed(1));
      }}
    }}

    function xPos(value) {{
      const labels = payload.singleMu ? payload.heights : payload.muValues;
      const span = Math.max(1, labels.length - 1);
      return pad.left + (value / span) * plotW;
    }}

    function yPos(value) {{
      return height - pad.bottom - (value / maxY) * plotH;
    }}

    function resizeCanvas() {{
      const rect = plotHost.getBoundingClientRect();
      const cssWidth = Math.max(640, Math.floor(rect.width));
      const cssHeight = Math.max(480, Math.floor(rect.height));
      const dpr = window.devicePixelRatio || 1;
      canvas.style.width = cssWidth + 'px';
      canvas.style.height = cssHeight + 'px';
      canvas.width = Math.max(1, Math.floor(cssWidth * dpr));
      canvas.height = Math.max(1, Math.floor(cssHeight * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      width = cssWidth;
      height = cssHeight;
      plotW = width - pad.left - pad.right;
      plotH = height - pad.top - pad.bottom;
    }}

    function hitTest(clientX, clientY) {{
      const rect = canvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      let best = null;
      let bestDist = Infinity;
      for (const point of payload.points) {{
        const dx = point.canvasX - x;
        const dy = point.canvasY - y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist <= Math.max(10, pointRadius + 6) && dist < bestDist) {{
          best = point;
          bestDist = dist;
        }}
      }}
      return best;
    }}

    function setText(id, value) {{
      document.getElementById(id).textContent = value;
    }}

    function openModal(point) {{
      const previewPath = point.previewRelPath || '';
      setText('modalScoreText', '字符正确率 ' + point.score.toFixed(4));
      document.getElementById('modalScoreDot').style.background = colorFor(point.score);
      setText('modalCharHeight', point.char_height_px + ' px');
      setText('modalMuP', String(point.mu_p));
      setText('modalRho', point.rho.toFixed(1));
      setText('modalPhase', '(' + point.phase_x + ', ' + point.phase_y + ')');
      setText('modalNoiseRepeat', String(point.noise_repeat));
      setText('modalFontName', point.font_name || '未知');
      setText('modalText', point.text);
      setText('modalOcrText', point.ocr_text || '(空)');
      setText('modalCer', point.cer.toFixed(4));
      setText('modalPreviewPath', previewPath || '(未生成)');
      if (previewPath) {{
        modalImage.src = encodeURI(previewPath);
        modalImage.hidden = false;
        modalImageEmpty.hidden = true;
      }} else {{
        modalImage.removeAttribute('src');
        modalImage.hidden = true;
        modalImageEmpty.hidden = false;
      }}
      modalBackdrop.classList.remove('hidden');
    }}

    function closeModal() {{
      modalBackdrop.classList.add('hidden');
    }}

    async function exportCurrentChart() {{
      const previousLabel = exportChartButton.textContent;
      exportChartButton.disabled = true;
      exportChartButton.textContent = '导出中...';
      try {{
        const stamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = 'mtfsnr_scatter_' + stamp + '.png';
        if (canvas.toBlob) {{
          const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
          if (!blob) {{
            throw new Error('toBlob failed');
          }}
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          link.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1500);
        }} else {{
          const link = document.createElement('a');
          link.href = canvas.toDataURL('image/png');
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          link.remove();
        }}
      }} finally {{
        exportChartButton.disabled = false;
        exportChartButton.textContent = previousLabel;
      }}
    }}

    function renderPlot() {{
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);
    ctx.save();
    ctx.translate(width * 0.53, height * 0.48);
    ctx.rotate(-0.46);
    ctx.fillStyle = 'rgba(90, 101, 112, 0.10)';
    ctx.font = '96px Microsoft YaHei';
    ctx.textAlign = 'center';
    ctx.fillText('y-g-jiang.github.io', 0, 0);
    ctx.restore();

    ctx.strokeStyle = 'rgba(28, 39, 51, 0.10)';
    ctx.lineWidth = 1;
    const xLabels = payload.singleMu ? payload.heights : payload.muValues;
    for (let i = 0; i < xLabels.length; i += 1) {{
      const x = xPos(i);
      ctx.beginPath();
      ctx.moveTo(x, pad.top);
      ctx.lineTo(x, height - pad.bottom);
      ctx.stroke();
    }}
    if (payload.singleHeight || payload.singleMu) {{
      for (let rho = 0.1; rho <= 1.0; rho += 0.1) {{
        const y = yPos(rho);
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(width - pad.right, y);
        ctx.stroke();
        ctx.fillStyle = '#4d5a69';
        ctx.font = '22px Microsoft YaHei';
        ctx.fillText(rho.toFixed(1), 52, y + 7);
      }}
    }} else {{
      for (let i = 0; i < payload.heights.length; i += 1) {{
        const y0 = yPos(i * payload.bandHeight + 0.1);
        const y1 = yPos(i * payload.bandHeight + 1.0);
        ctx.fillStyle = i % 2 === 0 ? 'rgba(18, 27, 38, 0.03)' : 'rgba(18, 27, 38, 0.015)';
        ctx.fillRect(pad.left, y1, plotW, y0 - y1);
        ctx.fillStyle = '#4d5a69';
        ctx.font = '24px Microsoft YaHei';
        ctx.fillText('字号=' + payload.heights[i] + ' px', 18, y1 + 30);
      }}
    }}

    ctx.fillStyle = '#243140';
    ctx.font = '24px Microsoft YaHei';
    for (let i = 0; i < xLabels.length; i += 1) {{
      const x = xPos(i);
      ctx.save();
      ctx.translate(x, height - pad.bottom + 20);
      ctx.rotate(-0.35);
      ctx.fillText(String(xLabels[i]), 0, 0);
      ctx.restore();
    }}

    ctx.save();
    ctx.translate(34, height / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('填充率 rho', 0, 0);
    ctx.restore();
    if (payload.singleMu) {{
      ctx.fillText('字符高度 px', width / 2 - 90, height - 18);
    }} else {{
      ctx.fillText('入射光子数 mu_p', width / 2 - 120, height - 18);
    }}

      payload.points.forEach((point) => {{
        point.canvasX = xPos(point.x);
        point.canvasY = yPos(point.y);
        ctx.beginPath();
        ctx.fillStyle = colorFor(point.score);
        ctx.globalAlpha = 1.0;
      ctx.arc(point.canvasX, point.canvasY, pointRadius, 0, Math.PI * 2);
        ctx.fill();
      }});
      ctx.globalAlpha = 1.0;
    }}
    canvas.addEventListener('mousemove', (event) => {{
      canvas.style.cursor = hitTest(event.clientX, event.clientY) ? 'pointer' : 'default';
    }});
    canvas.addEventListener('click', (event) => {{
      const point = hitTest(event.clientX, event.clientY);
      if (point) {{
        openModal(point);
      }}
    }});
    modalClose.addEventListener('click', closeModal);
    modalBackdrop.addEventListener('click', (event) => {{
      if (event.target === modalBackdrop) {{
        closeModal();
      }}
    }});
    pointSizeRange.addEventListener('input', () => {{
      setPointRadius(Number.parseFloat(pointSizeRange.value));
      renderPlot();
    }});
    exportChartButton.addEventListener('click', () => {{
      exportCurrentChart();
    }});
    window.addEventListener('keydown', (event) => {{
      if (event.key === 'Escape') {{
        closeModal();
      }}
    }});
    function redraw() {{
      resizeCanvas();
      renderPlot();
    }}
    loadPointRadius();
    window.addEventListener('resize', redraw);
    redraw();
  </script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

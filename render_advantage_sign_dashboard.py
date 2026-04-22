from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from html import escape
from pathlib import Path


BLUE = "#1f63ff"
RED = "#d83b3b"
GRAY = "#98a4b3"
WATERMARK = "y-g-jiang.github.io"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_advantage_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in _read_csv_rows(path):
        rows.append(
            {
                "base_mu_p": int(float(row["base_mu_p"])),
                "rho": float(row["rho"]),
                "char_height_px": int(float(row["char_height_px"])),
                "matched_mu_p": float(row["matched_mu_p"]),
                "coupled_mean_char_acc": float(row["coupled_mean_char_acc"]),
                "snr_only_mean_char_acc": float(row["snr_only_mean_char_acc"]),
                "char_acc_advantage": float(row["char_acc_advantage"]),
                "coupled_mean_cer": float(row["coupled_mean_cer"]),
                "snr_only_mean_cer": float(row["snr_only_mean_cer"]),
                "n_eval": int(float(row["n_eval"])),
                "coupled_mtf_nyquist": float(row["coupled_mtf_nyquist"]),
                "snr_only_mtf_nyquist": float(row["snr_only_mtf_nyquist"]),
            }
        )
    return rows


def _load_paired_rows(path: Path) -> dict[tuple[int, float, int], dict[str, float]]:
    if not path.exists():
        return {}

    out: dict[tuple[int, float, int], dict[str, float]] = {}
    for row in _read_csv_rows(path):
        key = (
            int(float(row["base_mu_p"])),
            float(row["rho"]),
            int(float(row["char_height_px"])),
        )
        out[key] = {
            "paired_cov_char_acc": float(row["paired_cov_char_acc"]),
            "paired_corr_char_acc": float(row["paired_corr_char_acc"]),
            "paired_mean_delta": float(row["paired_mean_delta"]),
            "paired_std_delta": float(row["paired_std_delta"]),
            "paired_win_rate": float(row["paired_win_rate"]),
            "paired_tie_rate": float(row["paired_tie_rate"]),
            "n_pairs": int(float(row["n_pairs"])),
        }
    return out


def write_advantage_sign_dashboard(
    advantage_rows: list[dict[str, object]],
    paired_rows: dict[tuple[int, float, int], dict[str, float]],
    output_path: Path,
) -> None:
    if not advantage_rows:
        return

    mu_values = sorted({int(row["base_mu_p"]) for row in advantage_rows})
    rho_values = sorted({float(row["rho"]) for row in advantage_rows})
    mu_index = {mu_p: idx for idx, mu_p in enumerate(mu_values)}
    max_abs_delta = max(abs(float(row["char_acc_advantage"])) for row in advantage_rows)
    max_abs_delta = max(max_abs_delta, 1e-9)

    points: list[dict[str, object]] = []
    positive_count = 0
    negative_count = 0
    zero_count = 0
    for row in sorted(advantage_rows, key=lambda item: (int(item["base_mu_p"]), float(item["rho"]))):
        delta = float(row["char_acc_advantage"])
        if delta > 0:
            sign = "positive"
            color = BLUE
            positive_count += 1
        elif delta < 0:
            sign = "negative"
            color = RED
            negative_count += 1
        else:
            sign = "zero"
            color = GRAY
            zero_count += 1

        pairing = paired_rows.get(
            (
                int(row["base_mu_p"]),
                float(row["rho"]),
                int(row["char_height_px"]),
            ),
            {},
        )
        points.append(
            {
                "x": mu_index[int(row["base_mu_p"])],
                "mu_p": int(row["base_mu_p"]),
                "rho": float(row["rho"]),
                "matched_mu_p": float(row["matched_mu_p"]),
                "char_height_px": int(row["char_height_px"]),
                "delta": delta,
                "absDelta": abs(delta),
                "deltaRatio": abs(delta) / max_abs_delta,
                "sign": sign,
                "color": color,
                "coupled_mean_char_acc": float(row["coupled_mean_char_acc"]),
                "snr_only_mean_char_acc": float(row["snr_only_mean_char_acc"]),
                "coupled_mean_cer": float(row["coupled_mean_cer"]),
                "snr_only_mean_cer": float(row["snr_only_mean_cer"]),
                "n_eval": int(row["n_eval"]),
                "coupled_mtf_nyquist": float(row["coupled_mtf_nyquist"]),
                "snr_only_mtf_nyquist": float(row["snr_only_mtf_nyquist"]),
                "paired_cov_char_acc": float(pairing.get("paired_cov_char_acc", 0.0)),
                "paired_corr_char_acc": float(pairing.get("paired_corr_char_acc", 0.0)),
                "paired_mean_delta": float(pairing.get("paired_mean_delta", delta)),
                "paired_std_delta": float(pairing.get("paired_std_delta", 0.0)),
                "paired_win_rate": float(pairing.get("paired_win_rate", 0.0)),
                "paired_tie_rate": float(pairing.get("paired_tie_rate", 0.0)),
                "n_pairs": int(pairing.get("n_pairs", 0)),
            }
        )

    best_positive = max(points, key=lambda item: item["delta"])
    worst_negative = min(points, key=lambda item: item["delta"])
    payload = {
        "muValues": mu_values,
        "rhoValues": rho_values,
        "positiveCount": positive_count,
        "negativeCount": negative_count,
        "zeroCount": zero_count,
        "bestPositive": {
            "mu_p": best_positive["mu_p"],
            "rho": best_positive["rho"],
            "delta": best_positive["delta"],
        },
        "worstNegative": {
            "mu_p": worst_negative["mu_p"],
            "rho": worst_negative["rho"],
            "delta": worst_negative["delta"],
        },
        "points": points,
    }
    updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>填充率优势蓝红散点</title>
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
      color: #172331;
    }}
    .wrap {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) clamp(320px, 24vw, 390px);
      gap: 18px;
      padding: 18px;
      box-sizing: border-box;
      height: 100vh;
    }}
    .panel {{
      background: #ffffff;
      border: 1px solid #d7dee7;
      border-radius: 14px;
      box-shadow: 0 10px 26px rgba(28, 42, 57, 0.08);
      overflow: hidden;
      min-height: 0;
    }}
    .plot-panel {{
      display: flex;
      flex-direction: column;
      padding: 14px;
    }}
    .plot-host {{
      flex: 1 1 auto;
      min-height: 0;
    }}
    .side-panel {{
      padding: 14px;
      overflow: auto;
    }}
    .title {{
      font-size: 22px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .meta {{
      color: #586678;
      font-size: 13px;
      line-height: 1.6;
      margin-bottom: 12px;
    }}
    canvas {{
      width: 100%;
      height: 100%;
      display: block;
      border: 1px solid #e2e8ef;
      border-radius: 12px;
      background: #ffffff;
    }}
    .legend-box {{
      border: 1px solid #e0e6ee;
      border-radius: 12px;
      background: #fbfcfe;
      padding: 12px 14px;
      margin-bottom: 12px;
    }}
    .legend-row {{
      display: grid;
      grid-template-columns: 18px 1fr;
      gap: 10px;
      align-items: start;
      margin-bottom: 10px;
      font-size: 13px;
      line-height: 1.6;
      color: #425162;
    }}
    .legend-dot {{
      width: 14px;
      height: 14px;
      border-radius: 999px;
      margin-top: 3px;
      border: 1px solid rgba(0, 0, 0, 0.12);
    }}
    .blue {{
      background: {BLUE};
    }}
    .red {{
      background: {RED};
    }}
    .gray {{
      background: {GRAY};
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-bottom: 12px;
    }}
    .summary-card {{
      border: 1px solid #e0e6ee;
      border-radius: 12px;
      padding: 12px;
      background: #ffffff;
    }}
    .summary-label {{
      font-size: 12px;
      color: #617082;
      margin-bottom: 6px;
    }}
    .summary-value {{
      font-size: 20px;
      font-weight: 700;
      color: #172331;
    }}
    .control-card {{
      border: 1px solid #e0e6ee;
      border-radius: 12px;
      padding: 12px 14px;
      background: #fafcff;
      margin-bottom: 12px;
    }}
    .control-title {{
      margin-bottom: 8px;
      font-size: 13px;
      font-weight: 700;
      color: #223243;
    }}
    .control-row {{
      display: grid;
      grid-template-columns: 1fr 56px;
      gap: 12px;
      align-items: center;
    }}
    .control-value {{
      text-align: right;
      color: #445261;
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }}
    input[type="range"] {{
      width: 100%;
      accent-color: #3558d8;
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
      margin-top: 10px;
    }}
    .control-button:disabled {{
      opacity: 0.65;
      cursor: progress;
    }}
    .detail-card {{
      border: 1px solid #dde4ec;
      border-radius: 12px;
      padding: 12px 14px;
      background: #fbfcfe;
    }}
    .detail-title {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 16px;
      font-weight: 700;
      color: #1c2936;
      margin-bottom: 10px;
    }}
    .detail-dot {{
      width: 14px;
      height: 14px;
      border-radius: 999px;
      border: 1px solid rgba(0, 0, 0, 0.12);
      flex: 0 0 auto;
    }}
    .detail-row {{
      display: grid;
      grid-template-columns: 118px 1fr;
      gap: 10px;
      font-size: 13px;
      line-height: 1.7;
      margin-bottom: 4px;
      color: #445261;
    }}
    .detail-row strong {{
      color: #172331;
      word-break: break-word;
    }}
    @media (max-width: 1180px) {{
      .wrap {{
        grid-template-columns: minmax(0, 1fr);
        grid-template-rows: minmax(0, 1fr) minmax(260px, 40vh);
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="panel plot-panel">
      <div class="title">填充率优势蓝红散点</div>
      <div class="meta">更新时间 {escape(updated)} | 每个点对应一个 `(mu_p, rho)` 条件。蓝色表示低填充率方案优于高填充率参考，红色表示相反。</div>
      <div id="plotHost" class="plot-host">
        <canvas id="plot" width="2400" height="1600"></canvas>
      </div>
    </section>
    <aside class="panel side-panel">
      <div class="legend-box">
        <div class="legend-row">
          <span class="legend-dot blue"></span>
          <span>蓝色点：低填充率方案的字符正确率高于高填充率参考，说明分辨率收益压过了信噪比损失。</span>
        </div>
        <div class="legend-row">
          <span class="legend-dot red"></span>
          <span>红色点：高填充率参考更好，说明这时主要还是信噪比占优。</span>
        </div>
        <div class="legend-row">
          <span class="legend-dot gray"></span>
          <span>灰色点：两者几乎相当。</span>
        </div>
      </div>
      <div class="summary-grid">
        <div class="summary-card">
          <div class="summary-label">蓝点数量</div>
          <div class="summary-value">{positive_count}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">红点数量</div>
          <div class="summary-value">{negative_count}</div>
        </div>
      </div>
      <div class="meta">
        最强蓝点：mu_p={int(best_positive["mu_p"])}, rho={float(best_positive["rho"]):.1f}, delta={float(best_positive["delta"]):+.4f}<br>
        最强红点：mu_p={int(worst_negative["mu_p"])}, rho={float(worst_negative["rho"]):.1f}, delta={float(worst_negative["delta"]):+.4f}
      </div>
      <div class="control-card">
        <div class="control-title">散点大小</div>
        <div class="control-row">
          <input id="pointSizeRange" type="range" min="2" max="18" step="0.2" value="6.0">
          <div id="pointSizeValue" class="control-value">6.0</div>
        </div>
        <button id="exportChartButton" class="control-button" type="button">导出当前大图</button>
      </div>
      <div class="detail-card">
        <div class="detail-title">
          <span id="detailDot" class="detail-dot blue"></span>
          <span id="detailTitle">点击一个点查看细节</span>
        </div>
        <div class="detail-row"><span>基础光子数</span><strong id="detailMu">-</strong></div>
        <div class="detail-row"><span>填充率 rho</span><strong id="detailRho">-</strong></div>
        <div class="detail-row"><span>匹配信号光子</span><strong id="detailMatchedMu">-</strong></div>
        <div class="detail-row"><span>字符高度</span><strong id="detailHeight">-</strong></div>
        <div class="detail-row"><span>正确率差值</span><strong id="detailDelta">-</strong></div>
        <div class="detail-row"><span>低填充率正确率</span><strong id="detailCoupled">-</strong></div>
        <div class="detail-row"><span>高填充率参考</span><strong id="detailControl">-</strong></div>
        <div class="detail-row"><span>低填充率 CER</span><strong id="detailCoupledCer">-</strong></div>
        <div class="detail-row"><span>高填充率 CER</span><strong id="detailControlCer">-</strong></div>
        <div class="detail-row"><span>低填充率 Nyquist MTF</span><strong id="detailCoupledMtf">-</strong></div>
        <div class="detail-row"><span>高填充率 Nyquist MTF</span><strong id="detailControlMtf">-</strong></div>
        <div class="detail-row"><span>配对 win rate</span><strong id="detailWinRate">-</strong></div>
        <div class="detail-row"><span>配对相关</span><strong id="detailCorr">-</strong></div>
        <div class="detail-row"><span>配对协方差</span><strong id="detailCov">-</strong></div>
        <div class="detail-row"><span>评估数量</span><strong id="detailCount">-</strong></div>
      </div>
    </aside>
  </div>
  <script>
    const payload = {json.dumps(payload, ensure_ascii=False)};
    const plotHost = document.getElementById('plotHost');
    const canvas = document.getElementById('plot');
    const ctx = canvas.getContext('2d');
    const pointSizeRange = document.getElementById('pointSizeRange');
    const pointSizeValue = document.getElementById('pointSizeValue');
    const exportChartButton = document.getElementById('exportChartButton');
    const pointSizeStorageKey = 'mtfsnr.advantageSignPointRadius';
    const pad = {{ left: 110, right: 30, top: 36, bottom: 88 }};
    let width = 0;
    let height = 0;
    let plotW = 0;
    let plotH = 0;
    let pointRadius = 6.0;
    let selectedPoint = null;

    function setText(id, value) {{
      document.getElementById(id).textContent = value;
    }}

    function colorForPoint(point) {{
      if (point.sign === 'positive') return '{BLUE}';
      if (point.sign === 'negative') return '{RED}';
      return '{GRAY}';
    }}

    function loadPointRadius() {{
      const raw = window.localStorage ? window.localStorage.getItem(pointSizeStorageKey) : null;
      const parsed = raw ? Number.parseFloat(raw) : Number.NaN;
      if (Number.isFinite(parsed)) {{
        pointRadius = Math.max(2, Math.min(18, parsed));
      }}
      pointSizeRange.value = pointRadius.toFixed(1);
      pointSizeValue.textContent = pointRadius.toFixed(1);
    }}

    function setPointRadius(value) {{
      pointRadius = Math.max(2, Math.min(18, value));
      pointSizeRange.value = pointRadius.toFixed(1);
      pointSizeValue.textContent = pointRadius.toFixed(1);
      if (window.localStorage) {{
        window.localStorage.setItem(pointSizeStorageKey, pointRadius.toFixed(1));
      }}
    }}

    function xPos(index) {{
      const span = Math.max(1, payload.muValues.length - 1);
      return pad.left + (index / span) * plotW;
    }}

    function yPos(rho) {{
      return height - pad.bottom - ((rho - 0.1) / 0.9) * plotH;
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
        if (dist <= Math.max(10, pointRadius + 5) && dist < bestDist) {{
          best = point;
          bestDist = dist;
        }}
      }}
      return best;
    }}

    function selectPoint(point) {{
      selectedPoint = point;
      document.getElementById('detailDot').style.background = colorForPoint(point);
      setText(
        'detailTitle',
        point.sign === 'positive'
          ? '低填充率方案更好'
          : (point.sign === 'negative' ? '高填充率参考更好' : '两者几乎相当')
      );
      setText('detailMu', String(point.mu_p));
      setText('detailRho', point.rho.toFixed(1));
      setText('detailMatchedMu', point.matched_mu_p.toFixed(3));
      setText('detailHeight', point.char_height_px + ' px');
      setText('detailDelta', (point.delta >= 0 ? '+' : '') + point.delta.toFixed(6));
      setText('detailCoupled', point.coupled_mean_char_acc.toFixed(6));
      setText('detailControl', point.snr_only_mean_char_acc.toFixed(6));
      setText('detailCoupledCer', point.coupled_mean_cer.toFixed(6));
      setText('detailControlCer', point.snr_only_mean_cer.toFixed(6));
      setText('detailCoupledMtf', point.coupled_mtf_nyquist.toFixed(6));
      setText('detailControlMtf', point.snr_only_mtf_nyquist.toFixed(6));
      setText('detailWinRate', point.paired_win_rate.toFixed(4));
      setText('detailCorr', point.paired_corr_char_acc.toFixed(6));
      setText('detailCov', point.paired_cov_char_acc.toFixed(6));
      setText('detailCount', String(point.n_pairs || point.n_eval));
      renderPlot();
    }}

    async function exportCurrentChart() {{
      const previousLabel = exportChartButton.textContent;
      exportChartButton.disabled = true;
      exportChartButton.textContent = '导出中...';
      try {{
        const stamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = 'advantage_sign_scatter_' + stamp + '.png';
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
      ctx.translate(width * 0.54, height * 0.47);
      ctx.rotate(-0.46);
      ctx.fillStyle = 'rgba(90, 101, 112, 0.10)';
      ctx.font = '92px Microsoft YaHei';
      ctx.textAlign = 'center';
      ctx.fillText('{WATERMARK}', 0, 0);
      ctx.restore();

      ctx.strokeStyle = 'rgba(25, 37, 49, 0.10)';
      ctx.lineWidth = 1;
      for (let i = 0; i < payload.muValues.length; i += 1) {{
        const x = xPos(i);
        ctx.beginPath();
        ctx.moveTo(x, pad.top);
        ctx.lineTo(x, height - pad.bottom);
        ctx.stroke();
      }}

      for (let index = 0; index < payload.rhoValues.length; index += 1) {{
        const rho = payload.rhoValues[index];
        const y = yPos(rho);
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(width - pad.right, y);
        ctx.stroke();
        ctx.fillStyle = '#506070';
        ctx.font = '21px Microsoft YaHei';
        ctx.textAlign = 'right';
        ctx.fillText(rho.toFixed(1), pad.left - 16, y + 7);
      }}

      ctx.fillStyle = '#213141';
      ctx.font = '22px Microsoft YaHei';
      ctx.textAlign = 'center';
      for (let i = 0; i < payload.muValues.length; i += 1) {{
        const x = xPos(i);
        ctx.save();
        ctx.translate(x, height - pad.bottom + 22);
        ctx.rotate(-0.35);
        ctx.fillText(String(payload.muValues[i]), 0, 0);
        ctx.restore();
      }}

      ctx.save();
      ctx.translate(36, height / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText('填充率 rho', 0, 0);
      ctx.restore();
      ctx.fillText('基础光子数 mu_p', width / 2, height - 16);

      for (const point of payload.points) {{
        point.canvasX = xPos(point.x);
        point.canvasY = yPos(point.rho);
        const isSelected = selectedPoint
          && selectedPoint.mu_p === point.mu_p
          && Math.abs(selectedPoint.rho - point.rho) < 1e-9;
        ctx.beginPath();
        ctx.fillStyle = colorForPoint(point);
        ctx.globalAlpha = 0.92;
        ctx.arc(point.canvasX, point.canvasY, pointRadius, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1.0;
        if (isSelected) {{
          ctx.lineWidth = 2.4;
          ctx.strokeStyle = '#14202c';
          ctx.stroke();
        }}
      }}
    }}

    canvas.addEventListener('mousemove', (event) => {{
      canvas.style.cursor = hitTest(event.clientX, event.clientY) ? 'pointer' : 'default';
    }});

    canvas.addEventListener('click', (event) => {{
      const point = hitTest(event.clientX, event.clientY);
      if (point) {{
        selectPoint(point);
      }}
    }});

    pointSizeRange.addEventListener('input', () => {{
      setPointRadius(Number.parseFloat(pointSizeRange.value));
      renderPlot();
    }});

    exportChartButton.addEventListener('click', () => {{
      exportCurrentChart();
    }});

    function redraw() {{
      resizeCanvas();
      renderPlot();
    }}

    loadPointRadius();
    window.addEventListener('resize', redraw);
    selectPoint(payload.points.reduce((best, point) => (
      Math.abs(point.delta) > Math.abs(best.delta) ? point : best
    )));
    redraw();
  </script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a blue/red HTML dashboard for fill-factor advantage.")
    parser.add_argument(
        "--input-dir",
        default="outputs/resolution_advantage_8px/baseline",
        help="Directory containing advantage_summary.csv and optional paired_statistics.csv.",
    )
    parser.add_argument(
        "--output-name",
        default="advantage_sign_dashboard.html",
        help="Output HTML filename under --input-dir.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    advantage_rows = _load_advantage_rows(input_dir / "advantage_summary.csv")
    paired_rows = _load_paired_rows(input_dir / "paired_statistics.csv")
    output_path = input_dir / args.output_name
    write_advantage_sign_dashboard(advantage_rows, paired_rows, output_path)
    print(f"Wrote {output_path.resolve()}")


if __name__ == "__main__":
    main()

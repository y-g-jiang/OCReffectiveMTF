# mtfsnr OCR Aperture Simulation

这个目录现在包含一个可运行的最小仿真框架，用来测试单色黑白传感器里“开口率变小时 MTF 提高、QE 降低”对 OCR 任务表现的影响。

当前默认常量：

- `eta_si = 0.85`
- `read_noise_e = 1.0`
- `QE_total = eta_si * rho`
- 单一字体为项目内置的 `license_plate_bahnschrift.ttf`
- 字符集只包含 `A-Z`

## 运行方式

快速冒烟：

```powershell
python run_experiment.py --preset smoke
```

稍大一点的起步扫描：

```powershell
python run_experiment.py --preset starter
```

自定义扫描网格：

```powershell
python run_experiment.py `
  --preset smoke `
  --mu-p 8 32 128 512 `
  --char-heights 4 6 8 12 16 `
  --phase-count 4 `
  --samples-per-condition 3 `
  --font-limit 2
```

## 输出内容

运行后会在 `outputs/<preset>/` 下生成：

- `detail_results.csv`
  每次 OCR 评估的逐条结果
- `aggregate_results.csv`
  按 `rho / mu_p / char_height_px` 聚合后的平均结果
- `best_rho_table.csv`
  宽表形式的最佳开口率矩阵
- `best_char_acc_table.csv`
  宽表形式的最佳字符正确率矩阵
- `char_acc_vs_rho.png`
  各字号下 `OCR score vs rho`
- `best_rho_heatmap.png`
  最优开口率热图
- `mtf_vs_char_acc.png`
  理论 aperture MTF50 与 OCR 分数散点图
- `chart_previews/`
  一小部分原始测试图预览
- `sensor_previews/`
  一小部分经过成像链退化后的 OCR 输入图

## 工程结构

- [run_experiment.py](run_experiment.py)
  主入口
- [mtfsnr_sim/config.py](mtfsnr_sim/config.py)
  默认配置与参数预设
- [mtfsnr_sim/chart_generator.py](mtfsnr_sim/chart_generator.py)
  随机字符串生成、字体渲染、亚像素相位偏移
- [mtfsnr_sim/sensor_model.py](mtfsnr_sim/sensor_model.py)
  aperture blur、QE、shot noise、read noise、量化
- [mtfsnr_sim/ocr_runner.py](mtfsnr_sim/ocr_runner.py)
  显式调用本机 Tesseract
- [mtfsnr_sim/analysis.py](mtfsnr_sim/analysis.py)
  CER、聚合和绘图

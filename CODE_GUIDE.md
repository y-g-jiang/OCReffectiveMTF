# 代码索引

这份文档按“入口脚本”和“核心模块”整理当前目录下所有 Python 文件，方便快速判断每个文件负责什么。

## 入口脚本

- [run_experiment.py](<C:\Users\姜尧耕\Downloads\mtfsnr\run_experiment.py:1>)
  通用实验主入口。负责读取命令行参数、构造实验任务、并行运行 OCR 仿真、输出 `detail_results.csv` / `aggregate_results.csv`、生成 PNG 图表、实时 HTML 面板，以及预览图。
  适合用在“常规扫描填充率、光子数、字号”的实验。

- [run_resolution_advantage_experiment.py](<C:\Users\姜尧耕\Downloads\mtfsnr\run_resolution_advantage_experiment.py:1>)
  “分辨率优势”专用主入口。它不是单纯跑 `rho` 扫描，而是显式比较两条支路：
  `coupled_fill_factor`：低填充率同时改变分辨率和 QE。
  `snr_only_matched`：保持 `rho=1.0` 的模糊，但把光子数降到 `base_mu_p * rho`。
  这个脚本还负责构造 `advantage_summary.csv`、`paired_statistics.csv`、优势热图、配对协方差/相关热图和总结文档。

- [rerender_outputs.py](<C:\Users\姜尧耕\Downloads\mtfsnr\rerender_outputs.py:1>)
  结果重渲染脚本。输入已有的 `detail_results.csv` 和 `aggregate_results.csv`，重新生成 PNG 图和 `live_dashboard.html`，不重跑 OCR。
  适合“只改图表外观或 HTML 界面，不改实验数据”的场景。

- [render_advantage_sign_dashboard.py](<C:\Users\姜尧耕\Downloads\mtfsnr\render_advantage_sign_dashboard.py:1>)
  蓝红优势仪表盘渲染脚本。读取 `advantage_summary.csv` 和可选的 `paired_statistics.csv`，生成“蓝点代表低填充率更优、红点代表对照更优”的独立 HTML 页面。
  适合“只看净优势正负，不看灰度分数散点”的场景。

## 核心模块

### 配置

- [mtfsnr_sim/config.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\config.py:1>)
  定义实验配置结构 `ExperimentConfig` 和默认 preset。
  这里统一管理：
  `eta_si=0.85`
  `read_noise_e=1.0`
  `oversample=16`
  `rho` 网格
  `mu_p` 网格
  `char_heights_px`
  `phase_count`
  OCR 白名单
  默认字体
  Tesseract 路径

- [mtfsnr_sim/__init__.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\__init__.py:1>)
  包入口。主要用于导出默认配置构造函数，内容很轻。

### 字图生成

- [mtfsnr_sim/chart_generator.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\chart_generator.py:1>)
  负责生成理想高分辨率测试图。
  主要职责：
  `generate_random_strings()`：生成随机字符串。
  `generate_permutation_strings()`：生成“字符表单次全排列”的字符串。
  `build_phase_offsets()`：生成离散相位点。
  `render_text_image()`：按指定字体和目标像素高度渲染超采样字图。
  `apply_integer_shift()`：在超采样域上施加相位偏移。

### 成像模型

- [mtfsnr_sim/sensor_model.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\sensor_model.py:1>)
  负责把理想字图变成传感器图像。
  主要职责：
  `simulate_capture()`：执行像素积分、下采样、QE 缩放、shot noise、read noise、量化和 OCR 放大。
  `theoretical_metrics()`：给出理论 `mtf_nyquist` 和 `aperture_f50_cpp`。
  `SensorCapture`：封装输出图和理论指标。
  当前核心假设是 `QE_total = eta_si * rho`，同时 `rho` 也决定像素积分宽度。

### OCR 封装

- [mtfsnr_sim/ocr_runner.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\ocr_runner.py:1>)
  Tesseract 调用层。
  主要职责：
  `run_tesseract()`：把灰度图写到 worker 临时目录，调用本机 Tesseract，关闭词典补偿，按白名单过滤输出。
  `OCRResult`：返回清洗后的文本和原始文本。

### 单任务求值

- [mtfsnr_sim/evaluator.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\evaluator.py:1>)
  通用实验的单任务执行器。
  主要职责：
  `EvalTask`：描述一个“固定字图、固定相位、扫描多组 `mu_p` 和 `rho`”的任务。
  `_render_cached()` / `_shifted_scene_cached()`：缓存渲染结果，减少重复计算。
  `evaluate_task()`：对每个任务运行传感器仿真、OCR、CER/`char_acc` 计算，并可输出单点预览图。

### 结果分析与可视化

- [mtfsnr_sim/analysis.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\analysis.py:1>)
  通用实验的分析和可视化中心模块。
  主要职责：
  `write_results_csv()`：统一写 CSV。
  `aggregate_condition_rows()`：把 detail 结果聚合成条件级结果。
  `write_metric_table()` / `write_best_tables()`：输出 `best_rho_table.csv` 等表格。
  `plot_score_vs_rho()`：画 `char_acc vs rho` 曲线。
  `plot_best_rho_heatmap()`：画最优 `rho` 热图。
  `plot_mtf_vs_score()`：画理论 MTF 与 OCR 得分关系图。
  `plot_huge_sample_score_scatter()`：画大散点图。
  `write_live_html_dashboard()`：生成交互 HTML 面板。

  这个文件现在还包含大量界面逻辑：
  白底全屏自适应布局。
  半透明水印 `y-g-jiang.github.io`。
  散点大小滑杆。
  导出当前大图按钮。
  点击点查看对应预览图和分数弹窗。
  当前灰度色阶映射。

## 各脚本之间的调用关系

### 通用实验链路

1. [run_experiment.py](<C:\Users\姜尧耕\Downloads\mtfsnr\run_experiment.py:1>)
   读取参数，调用 [mtfsnr_sim/config.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\config.py:1>) 生成配置。
2. [mtfsnr_sim/chart_generator.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\chart_generator.py:1>)
   生成高分辨率字图和相位偏移。
3. [mtfsnr_sim/evaluator.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\evaluator.py:1>)
   驱动单任务。
4. [mtfsnr_sim/sensor_model.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\sensor_model.py:1>)
   生成传感器图像。
5. [mtfsnr_sim/ocr_runner.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\ocr_runner.py:1>)
   调用 OCR。
6. [mtfsnr_sim/analysis.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\analysis.py:1>)
   聚合结果、画图、生成 HTML。

### 分辨率优势链路

1. [run_resolution_advantage_experiment.py](<C:\Users\姜尧耕\Downloads\mtfsnr\run_resolution_advantage_experiment.py:1>)
   自己定义 `ComparisonTask` 和专用聚合逻辑。
2. 它仍复用：
   [mtfsnr_sim/chart_generator.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\chart_generator.py:1>)
   [mtfsnr_sim/sensor_model.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\sensor_model.py:1>)
   [mtfsnr_sim/ocr_runner.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\ocr_runner.py:1>)
3. 然后额外计算：
   `advantage_summary.csv`
   `paired_statistics.csv`
   `best_advantage_table.csv`
   `advantage_heatmap.png`
   `paired_cov_heatmap.png`
   `paired_corr_heatmap.png`
   `SUMMARY.md`
4. 如果只想把优势正负渲染成蓝红 HTML，则再调用
   [render_advantage_sign_dashboard.py](<C:\Users\姜尧耕\Downloads\mtfsnr\render_advantage_sign_dashboard.py:1>)

## 如果你想改某件事，该看哪个文件

- 改默认实验参数、光子数网格、字号网格：看 [mtfsnr_sim/config.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\config.py:1>)
- 改字符集、随机字符串、单次全排列逻辑：看 [mtfsnr_sim/chart_generator.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\chart_generator.py:1>)
- 改成像物理模型、QE 与填充率关系、理想 SNR 模式：看 [mtfsnr_sim/sensor_model.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\sensor_model.py:1>)
- 改 OCR 白名单、PSM、Tesseract 调用方式：看 [mtfsnr_sim/ocr_runner.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\ocr_runner.py:1>)
- 改单个样本点怎样被评估、是否输出预览图：看 [mtfsnr_sim/evaluator.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\evaluator.py:1>)
- 改通用实验的输出表、PNG、HTML、交互界面：看 [mtfsnr_sim/analysis.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\analysis.py:1>)
- 跑常规实验：看 [run_experiment.py](<C:\Users\姜尧耕\Downloads\mtfsnr\run_experiment.py:1>)
- 跑“低填充率真实优势 vs 仅降 SNR 对照”实验：看 [run_resolution_advantage_experiment.py](<C:\Users\姜尧耕\Downloads\mtfsnr\run_resolution_advantage_experiment.py:1>)
- 只重画旧结果：看 [rerender_outputs.py](<C:\Users\姜尧耕\Downloads\mtfsnr\rerender_outputs.py:1>)
- 只输出蓝红优势页面：看 [render_advantage_sign_dashboard.py](<C:\Users\姜尧耕\Downloads\mtfsnr\render_advantage_sign_dashboard.py:1>)

## 当前目录下的 Python 文件总表

- [run_experiment.py](<C:\Users\姜尧耕\Downloads\mtfsnr\run_experiment.py:1>)
- [run_resolution_advantage_experiment.py](<C:\Users\姜尧耕\Downloads\mtfsnr\run_resolution_advantage_experiment.py:1>)
- [rerender_outputs.py](<C:\Users\姜尧耕\Downloads\mtfsnr\rerender_outputs.py:1>)
- [render_advantage_sign_dashboard.py](<C:\Users\姜尧耕\Downloads\mtfsnr\render_advantage_sign_dashboard.py:1>)
- [mtfsnr_sim/__init__.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\__init__.py:1>)
- [mtfsnr_sim/config.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\config.py:1>)
- [mtfsnr_sim/chart_generator.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\chart_generator.py:1>)
- [mtfsnr_sim/sensor_model.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\sensor_model.py:1>)
- [mtfsnr_sim/ocr_runner.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\ocr_runner.py:1>)
- [mtfsnr_sim/evaluator.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\evaluator.py:1>)
- [mtfsnr_sim/analysis.py](<C:\Users\姜尧耕\Downloads\mtfsnr\mtfsnr_sim\analysis.py:1>)

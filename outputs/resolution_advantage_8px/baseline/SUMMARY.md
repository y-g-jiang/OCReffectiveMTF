# Resolution-Advantage Confidence Analysis

## 1. 问题定义

本分析旨在回答如下问题：

> 在当前实验设定下，当填充率 $\rho$ 降低时，系统虽然损失了量子效率与信噪比，但同时获得了更窄的像素积分核与更高的传感器几何分辨率。  
> 相比于一个“仅承受同等信号预算下降、但不获得分辨率收益”的对照系统，低填充率方案是否能够以统计上可信的方式获得更高的 OCR 检出表现？

当前对照的两支实验条件为：

1. `coupled_fill_factor`
   - 填充率取 $\rho<1$
   - 总量子效率满足
     $$
     \eta_{\text{total}}=\eta_{\text{si}}\rho
     $$
   - 像素有效积分宽度随 $\rho$ 缩小，因此具有更高的几何 MTF。

2. `snr_only_matched`
   - 保持模糊核固定为 $\rho=1$
   - 将入射光子数缩减为
     $$
     \mu_p^{\text{matched}}=\mu_p^{\text{base}}\rho
     $$
   - 因而其总信号预算与低填充率方案处于同一量级，但不获得分辨率收益。

因此，本分析比较的是：

> “低填充率带来的真实分辨率收益”  
> 与  
> “仅仅降低信号预算所造成的 SNR 下降”

之间的净效应。

相关实验结果位于：

- [detail_results.csv](<C:\Users\姜尧耕\Downloads\mtfsnr\outputs\resolution_advantage_8px\baseline\detail_results.csv:1>)
- [advantage_summary.csv](<C:\Users\姜尧耕\Downloads\mtfsnr\outputs\resolution_advantage_8px\baseline\advantage_summary.csv:1>)
- [paired_statistics.csv](<C:\Users\姜尧耕\Downloads\mtfsnr\outputs\resolution_advantage_8px\baseline\paired_statistics.csv:1>)

## 2. 配对设计

本实验采用**配对比较**。对于每一个条件 $(\mu_p,\rho,h)$，都在相同的：

- 字符串内容
- 相位偏移 $(\phi_x,\phi_y)$
- 噪声重复编号 $r$

下，同时生成：

- 低填充率版本 `coupled_fill_factor`
- 高填充率参考版本 `snr_only_matched`

因此，每个条件都可以形成一组配对差值：

$$
\Delta_i = s_i^{\text{low-fill}} - s_i^{\text{control}}
$$

其中 $s_i$ 为第 $i$ 个样本点的字符正确率 `char_acc`。

若 $\Delta_i>0$，则说明在该配对样本上，低填充率方案优于高填充率参考；若 $\Delta_i<0$，则相反。

对每个条件，本实验共有

$$
n = 5\times 5\times 2 = 50
$$

个配对样本。

## 3. 置信度分析的数学指标

### 3.1 平均优势

最基本的统计量是配对差值均值：

$$
\bar{\Delta}=\frac{1}{n}\sum_{i=1}^{n}\Delta_i
$$

其物理含义非常直接：

- $\bar{\Delta}>0$：低填充率平均更优
- $\bar{\Delta}<0$：高填充率参考平均更优

但 $\bar{\Delta}$ 本身并不足以表达“可信度”，因为它不包含波动范围。

### 3.2 Bootstrap 置信区间

对配对差值集合 $\{\Delta_i\}_{i=1}^n$ 进行有放回重采样，得到第 $b$ 次 bootstrap 平均值：

$$
\bar{\Delta}^{*(b)}=\frac{1}{n}\sum_{i=1}^{n}\Delta_{I_i^{(b)}}
$$

其中 $I_i^{(b)}$ 为第 $b$ 次重采样的索引。

令总重采样次数为 $B$，则 $95\%$ bootstrap 置信区间定义为：

$$
\mathrm{CI}_{95}=
\left[
Q_{0.025}\big(\bar{\Delta}^{*(1)},\ldots,\bar{\Delta}^{*(B)}\big),
Q_{0.975}\big(\bar{\Delta}^{*(1)},\ldots,\bar{\Delta}^{*(B)}\big)
\right]
$$

本分析采用 $B=20000$ 次 bootstrap 重采样。

解释规则如下：

- 若 $\mathrm{CI}_{95}$ 全部大于 $0$，则可认为“低填充率更优”具有较强统计支持。
- 若 $\mathrm{CI}_{95}$ 全部小于 $0$，则可认为“高填充率参考更优”具有较强统计支持。
- 若区间跨越 $0$，则该点只能视为不确定或证据不足。

### 3.3 Bootstrap 优势概率

为了给出更直观的“置信度”量，本分析定义：

$$
P_{\text{boot}}(\bar{\Delta}>0)=
\frac{1}{B}
\sum_{b=1}^{B}
\mathbf{1}\left(\bar{\Delta}^{*(b)}>0\right)
$$

这个量可以理解为：

> 在 bootstrap 重采样意义下，低填充率平均优势为正的比例。

需要强调的是，它不是严格意义上的贝叶斯后验概率，但作为工程上直观的“置信度指标”非常有用。

### 3.4 Sign Test

记

$$
W=\sum_{i=1}^{n}\mathbf{1}(\Delta_i>0),\qquad
L=\sum_{i=1}^{n}\mathbf{1}(\Delta_i<0),\qquad
T=\sum_{i=1}^{n}\mathbf{1}(\Delta_i=0)
$$

只考虑非零差值，得到有效样本数：

$$
N_d=W+L
$$

在零假设

$$
H_0:\Pr(\Delta_i>0)=0.5
$$

下，$W$ 服从参数为 $(N_d,0.5)$ 的二项分布，因此单侧 sign test 的 $p$ 值可写为：

$$
p_{\text{sign}}=
\Pr\left(X\ge W \mid X\sim \mathrm{Binomial}(N_d,0.5)\right)
$$

该检验只关注“赢的次数是否足够多”，不关心每次赢多少，因此对离群值和非高斯分布较稳健。

### 3.5 Wilcoxon Signed-Rank Test

令非零差值为 $\Delta_i\neq 0$，定义其秩为 $\mathrm{rank}(|\Delta_i|)$。Wilcoxon 正秩和统计量为：

$$
W^+ = \sum_{\Delta_i>0}\mathrm{rank}(|\Delta_i|)
$$

在单侧备择假设

$$
H_1:\mathrm{median}(\Delta_i)>0
$$

下，较小的 $p$ 值表示低填充率方案不仅赢得次数更多，而且赢得幅度也具有系统性。

与 sign test 相比，Wilcoxon 检验同时利用了“方向信息”和“幅度信息”，对本实验这类离散、界限化的 OCR 分数非常合适。

### 3.6 配对效应量

为了描述优势的实际强弱，本分析使用配对效应量

$$
d_z=\frac{\bar{\Delta}}{s_{\Delta}}
$$

其中

$$
s_{\Delta}=
\sqrt{
\frac{1}{n-1}
\sum_{i=1}^{n}
\left(\Delta_i-\bar{\Delta}\right)^2
}
$$

通常可作如下粗略解释：

- $|d_z|<0.2$：很弱
- $0.2\le |d_z|<0.5$：小到中等
- $0.5\le |d_z|<0.8$：中等
- $|d_z|\ge 0.8$：较强

### 3.7 Covariance / Correlation 的角色

此前已计算配对协方差与相关系数：

$$
\mathrm{Cov}(X,Y)=\frac{1}{n-1}\sum_{i=1}^{n}(x_i-\bar{x})(y_i-\bar{y})
$$

$$
\mathrm{Corr}(X,Y)=\frac{\mathrm{Cov}(X,Y)}{s_x s_y}
$$

其中 $X=s_i^{\text{low-fill}}$，$Y=s_i^{\text{control}}$。

这些量的作用是：

- 判断两种成像条件下“样本难易顺序”是否保持一致
- 帮助解释是否存在结构性分辨率变化

但它们**不是“低填充率更优置信度”的主指标**。  
因此，学术汇报中应将它们放在辅助解释层，而非主结论层。

## 4. 推荐的判定准则

对于单个条件 $(\mu_p,\rho,h)$，若希望以较稳健的方式认定“低填充率更优”，建议同时满足：

1. $\bar{\Delta}>0$
2. $\mathrm{CI}_{95}$ 全部大于 $0$
3. $P_{\text{boot}}(\bar{\Delta}>0)\ge 0.975$
4. $p_{\text{sign}}<0.05$
5. $p_{\text{wilcoxon}}<0.05$

其中：

- `CI` 与 `P_boot` 是最直观的置信度表达
- `sign test` 提供方向上的稳健检验
- `Wilcoxon` 提供带幅度信息的非参数支持

如果只选择一个最接近“置信度”的单值指标，建议报告：

$$
P_{\text{boot}}(\bar{\Delta}>0)
$$

并同时附上 $\mathrm{CI}_{95}$。

## 5. 当前实验结果摘要

本分析针对输出目录 [outputs/resolution_advantage_8px/baseline](<C:\Users\姜尧耕\Downloads\mtfsnr\outputs\resolution_advantage_8px\baseline>) 的结果进行后处理。

总体统计如下：

- 总条件数：$250$
- 其中 $\mathrm{CI}_{95}>0$ 的条件数：$50$
- 其中 $\mathrm{CI}_{95}<0$ 的条件数：$4$
- 其余跨越 $0$ 的条件数：$196$
- `sign test` 单侧 $p<0.05$ 的条件数：$68$
- `Wilcoxon` 单侧 $p<0.05$ 的条件数：$64$

这说明：

1. 低填充率更优的情形并非个别离群点，而是在一部分工况下具有可重复的统计支持。
2. 但大多数条件仍处于“不确定区”，即当前样本量下尚不足以作出强结论。
3. 明确支持“高填充率更优”的条件数较少，仅有 $4$ 个条件在 bootstrap 置信区间意义下完全落于负侧。

## 6. 代表性工况

下表列出若干有代表性的点：

| base $\mu_p$ | $\rho$ | $\bar{\Delta}$ | 95% CI | $P_{\text{boot}}(\bar{\Delta}>0)$ | $p_{\text{sign}}$ | $p_{\text{wilcoxon}}$ | $d_z$ | wins / losses / ties |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 0.2 | +0.133333 | [+0.081212, +0.183636] | 1.0000 | 8.86e-08 | 7.25e-06 | +0.720 | 41 / 6 / 3 |
| 64 | 0.4 | +0.152727 | [+0.066667, +0.243030] | 0.9997 | 9.76e-03 | 1.35e-03 | +0.474 | 29 / 13 / 8 |
| 215 | 0.1 | +0.195152 | [+0.081212, +0.306667] | 0.9998 | 7.25e-04 | 2.21e-04 | +0.478 | 31 / 10 / 9 |
| 23 | 0.8 | -0.101212 | [-0.205455, +0.003636] | 0.0295 | 9.12e-01 | 9.37e-01 | -0.262 | 14 / 21 / 15 |
| 4 | 0.8 | +0.016970 | [-0.003636, +0.037576] | 0.9475 | 1.34e-01 | 4.67e-02 | +0.228 | 24 / 16 / 10 |

这些结果可作如下解释：

- `mu_p=32, rho=0.2`：这是一个**强阳性工况**。均值优势显著为正，置信区间完全落于正侧，且两种非参数检验均显著。
- `mu_p=64, rho=0.4`：同样属于**稳定的正优势工况**，说明中等光子数区间确实存在“分辨率收益压过 SNR 损失”的区域。
- `mu_p=215, rho=0.1`：优势幅度很大，说明在部分高光子数与极低填充率组合下，分辨率收益仍可非常明显。
- `mu_p=23, rho=0.8`：虽然均值差为负，但置信区间仍跨越零，因此更适合表述为“倾向于高填充率参考更优”，而非“已经被强证据证实”。
- `mu_p=4, rho=0.8`：优势很弱且区间跨零，可归入“方向略偏正，但证据不足”的类别。

## 7. 学术表达上的建议

若将本文结果写入论文或技术报告，建议避免仅使用“某点均值更高”这类表述，而应采用如下范式：

> 对每个 $(\mu_p,\rho)$ 条件，基于 $n=50$ 个配对样本构造字符正确率差值 $\Delta_i$。  
> 采用 20000 次 paired bootstrap 估计 $\bar{\Delta}$ 的 $95\%$ 置信区间，并辅以单侧 sign test 和 Wilcoxon signed-rank test 进行稳健性验证。  
> 当 $\mathrm{CI}_{95}>0$ 且 $p_{\text{sign}}<0.05$、$p_{\text{wilcoxon}}<0.05$ 时，将该条件判定为“低填充率方案具有统计支持的分辨率优势”。

这种写法比单纯报告平均分数更严谨，也更容易与后续不同 OCR、不同字号、不同噪声模型的结果进行横向比较。

## 8. 结论

在当前实验设定下，“低填充率采样更优”并不是一个只能凭肉眼判断的现象，而是可以用配对统计严格表述的命题。  
从统计学角度看，最值得作为主指标报告的是：

1. 配对均值优势 $\bar{\Delta}$
2. $95\%$ bootstrap 置信区间
3. $P_{\text{boot}}(\bar{\Delta}>0)$
4. 单侧 sign test 与 Wilcoxon signed-rank test 的 $p$ 值
5. 配对效应量 $d_z$

其中：

- `cov/corr` 适合解释“样本难易结构是否改变”
- `CI`、`P_boot`、`sign test`、`Wilcoxon` 才真正对应“低填充率更优的置信度”

因此，若后续需要在交互式 HTML 或结果表中增加“置信度”字段，建议优先加入：

- `P_boot(delta > 0)`
- `95% CI`
- `sign p`
- `Wilcoxon p`
- `d_z`

这五项已经足以构成一套较完整、较学术化的置信度分析框架。

## 9. 完整实验流程

为了将“填充率下降是否带来真实分辨率优势”这一问题转化为可重复的任务型实验，本文采用如下完整流程。

### 9.1 目标字符串的构造

首先，取给定字符表中的全部字符，进行一次随机排列，并将其排成单行字符串作为测试目标。若字符表记为

$$
\mathcal{A}=\{a_1,a_2,\ldots,a_M\}
$$

则目标字符串可记为

$$
T=\pi(\mathcal{A}),
$$

其中 $\pi(\cdot)$ 表示一个随机排列算子。

在当前实验实现中，为了避免 `I/1` 等先天难以区分的字符对统计造成额外混淆，默认字符表取为

$$
\mathcal{A}=\{0,2,3,4,5,6,7,8,9,A,B,\ldots,H,J,\ldots,N,P,\ldots,Z\}.
$$

也就是说，实验并不依赖语言模型或词典结构，而是使用一条人工构造的、无语义先验的单行字符序列作为靶标，从而尽可能将性能差异归因于成像与采样过程本身。

### 9.2 高分辨率字图的生成

对于每个待测字符高度 $h$，先在高分辨率网格上渲染对应字符串。设超采样倍数为 $s$，则传感器像素网格上的单个像素被扩展为 $s\times s$ 的高分辨率子网格。当前实现中取

$$
s=16.
$$

因此，理想目标图像首先在超采样域内生成，以尽可能减小字体栅格化误差，并为后续的相位平移与像素积分提供统一输入。

若记高分辨率理想图像为

$$
I_{\mathrm{hr}}(x,y),
$$

则它在此阶段尚未叠加传感器积分、量子效率损失或噪声，仅表示理想黑白字形分布。

### 9.3 亚像素相位扫描

为了避免实验结论依赖于偶然的像素对齐位置，本文对每个条件都进行二维亚像素相位扫描。设相位集合为

$$
\Phi_x=\Phi_y=\{\phi_1,\phi_2,\ldots,\phi_K\},
$$

则每个条件下都对

$$
(\phi_x,\phi_y)\in\Phi_x\times\Phi_y
$$

的全部组合进行评估。当前实验中取

$$
K=5,
$$

因此每个条件包含 $5\times 5=25$ 个相位组合。

在具体实现中，相位偏移通过对高分辨率图像进行整数子像素平移完成，从而保证不同实验分支之间共享完全相同的相位条件。

### 9.4 低填充率支路与匹配对照支路

对每一个基础光子数 $\mu_p^{\text{base}}$、填充率 $\rho$ 与相位组合，本文同时生成两条成像支路。

#### (1) 低填充率真实支路

这一支路直接让填充率同时影响：

- 像素积分宽度
- 总量子效率
- 因此同时影响分辨率与 SNR

像素有效积分宽度写为

$$
w(\rho)=p\sqrt{\rho},
$$

其中 $p$ 为像素 pitch。

总量子效率写为

$$
\eta_{\mathrm{total}}=\eta_{\mathrm{si}}\rho.
$$

当前实验中固定

$$
\eta_{\mathrm{si}}=0.85.
$$

若经过像素积分与下采样后的归一化灰度图像记为 $L(x,y;\rho)$，则对应像素上的平均电子数为

$$
\bar{N}_e(x,y;\rho)=L(x,y;\rho)\,\eta_{\mathrm{si}}\rho\,\mu_p^{\text{base}}.
$$

实际电子数则满足

$$
N_e(x,y;\rho)\sim \mathrm{Poisson}\big(\bar{N}_e(x,y;\rho)\big)+\mathcal{N}(0,\sigma_r^2),
$$

其中读噪固定为

$$
\sigma_r=1\ \mathrm{e^-}.
$$

#### (2) SNR-only 匹配对照支路

为了构造“只损失信号预算、不获得分辨率提升”的对照，对照支路固定使用

$$
\rho_{\mathrm{ctrl}}=1,
$$

即保留宽积分核与较低的几何分辨率；但同时将基础光子数缩减为

$$
\mu_p^{\text{matched}}=\mu_p^{\text{base}}\rho.
$$

于是，对照支路的平均电子数写为

$$
\bar{N}_e^{\text{ctrl}}(x,y)=L(x,y;1)\,\eta_{\mathrm{si}}\cdot 1\cdot \mu_p^{\text{base}}\rho.
$$

这意味着两条支路处于相近的总信号预算量级，但只有低填充率支路获得了更窄像素积分核所带来的空间分辨率收益。

### 9.5 噪声重复与 OCR 识别

为了稳定统计结果，本文对每个条件额外进行噪声重复。设噪声重复次数为 $R$，则每个 $(\mu_p,\rho,\phi_x,\phi_y)$ 条件会重复采样

$$
r=1,2,\ldots,R.
$$

当前实现中取

$$
R=2.
$$

因此，每个 $(\mu_p,\rho)$ 条件总共对应

$$
5\times 5\times 2 = 50
$$

个配对样本。

每张退化后图像都会送入 OCR 引擎识别。设目标字符串为 $T$，OCR 输出为 $\hat{T}$，则字符错误率定义为

$$
\mathrm{CER}(T,\hat{T})=
\frac{d_{\mathrm{Lev}}(T,\hat{T})}{|T|},
$$

其中 $d_{\mathrm{Lev}}$ 为 Levenshtein 编辑距离。对应的字符正确率为

$$
\mathrm{char\_acc}=1-\mathrm{CER}.
$$

在本文全部统计与置信度分析中，`char_acc` 被视为主要评分量。

### 9.6 参数扫描

在当前这轮“分辨率优势”实验中，主要扫描参数为：

- 字符高度：固定为 `8 px`
- 填充率：
  $$
  \rho\in\{0.1,0.2,\ldots,1.0\}
  $$
- 基础光子数：
  $$
  \mu_p^{\text{base}}\in\{4,5,6,7,8,10,11,13,16,19,23,27,32,38,45,54,64,76,91,108,128,152,181,215,256\}
  $$

因此，本实验比较的不是单个孤立点，而是一个关于 $(\mu_p,\rho)$ 的二维参数曲面。

## 10. 最终处理步骤

从实验执行到最终结论生成，本文采用如下后处理流程。

### 10.1 单样本结果写出

首先，对每一张 OCR 输入图像保存单条记录，包括：

- 所属支路
- 基础光子数
- 填充率
- 字符高度
- 相位坐标
- 噪声重复编号
- OCR 输出
- `CER`
- `char_acc`

这些结果写入 [detail_results.csv](<C:\Users\姜尧耕\Downloads\mtfsnr\outputs\resolution_advantage_8px\baseline\detail_results.csv:1>)。

### 10.2 条件聚合

随后，在每个条件 $(\mu_p,\rho,h,\text{condition})$ 上对单样本分数求均值，得到条件级结果：

$$
\bar{s}(\mu_p,\rho,h,c)=\frac{1}{n}\sum_{i=1}^{n}s_i(\mu_p,\rho,h,c),
$$

其中 $c$ 表示成像支路。

聚合结果写入 [aggregate_by_condition.csv](<C:\Users\姜尧耕\Downloads\mtfsnr\outputs\resolution_advantage_8px\baseline\aggregate_by_condition.csv:1>)。

### 10.3 构造净优势

对每一个 $(\mu_p,\rho,h)$，分别取两支路的平均字符正确率，构造净优势：

$$
\Delta(\mu_p,\rho,h)=
\bar{s}^{\text{low-fill}}(\mu_p,\rho,h)-
\bar{s}^{\text{control}}(\mu_p,\rho,h).
$$

其含义如下：

- $\Delta>0$：低填充率方案更优
- $\Delta<0$：高填充率参考更优

这一结果写入 [advantage_summary.csv](<C:\Users\姜尧耕\Downloads\mtfsnr\outputs\resolution_advantage_8px\baseline\advantage_summary.csv:1>)，并据此绘制：

- [advantage_heatmap.png](<C:\Users\姜尧耕\Downloads\mtfsnr\outputs\resolution_advantage_8px\baseline\advantage_heatmap.png>)
- [advantage_sign_dashboard.html](<C:\Users\姜尧耕\Downloads\mtfsnr\outputs\resolution_advantage_8px\baseline\advantage_sign_dashboard.html>)

其中后者以蓝色点表示 $\Delta>0$，以红色点表示 $\Delta<0$。

### 10.4 配对统计与置信度分析

在净优势的基础上，再回到单样本配对层面，构造

$$
\Delta_i=s_i^{\text{low-fill}}-s_i^{\text{control}},
$$

并进一步计算：

- $\bar{\Delta}$
- $95\%$ bootstrap 置信区间
- $P_{\text{boot}}(\bar{\Delta}>0)$
- 单侧 sign test
- 单侧 Wilcoxon signed-rank test
- 配对效应量 $d_z$

这些量共同构成本文所谓的“低填充率采样更优的置信度分析”。

### 10.5 最终判读

在最终判读阶段，本文不再单纯依据某个条件下的平均分高低作结论，而是将每个点归入下列三类之一：

1. **统计支持的低填充率优势区**
   - $\bar{\Delta}>0$
   - $\mathrm{CI}_{95}>0$
   - 且非参数检验显著

2. **统计支持的高填充率优势区**
   - $\bar{\Delta}<0$
   - $\mathrm{CI}_{95}<0$

3. **不确定区**
   - 置信区间跨越零
   - 或均值虽偏正、但统计支持不足

因此，最终结论不是一个单独的“最优填充率常数”，而是一张关于光子数、填充率与任务表现之间关系的统计判别图。

## 11. 可直接用于论文方法部分的概述段

若需要在论文或技术报告中用一段较紧凑的文字概述整个实验，可使用如下表述：

> 具体而言，我们首先从给定字符表中生成随机排列的一行字符串，并在 16 倍超采样网格上渲染理想黑白字图。随后，对每一个基础光子数 $\mu_p$、填充率 $\rho$、二维亚像素相位 $(\phi_x,\phi_y)$ 以及噪声重复编号 $r$，同时生成两条成像支路：其一为真实低填充率支路，其中 $\rho$ 同时决定像素积分宽度与总量子效率；其二为 SNR-only 匹配对照支路，其中模糊核固定为 $\rho=1$，但基础光子数缩减为 $\mu_p\rho$，从而在不获得分辨率收益的前提下复现与低填充率支路相近的信号预算。对每一张退化图像，使用同一 OCR 引擎进行识别，并以字符错误率和字符正确率作为任务性能指标。最后，在每个 $(\mu_p,\rho)$ 条件下构造配对差值 $\Delta_i=s_i^{\text{low-fill}}-s_i^{\text{control}}$，并采用 paired bootstrap、sign test、Wilcoxon signed-rank test 以及配对效应量对“低填充率采样是否具有统计支持的分辨率优势”进行定量评估。  

这段概述与前文的统计定义、公式推导和结果表述是相互一致的，因此可以直接作为“实验方法”或“统计分析”章节的骨架。

# 孢子扩散预测引擎（lib/dispersion/）技术文档

> 版本 v2.0 · 2026-08-29 · 配合比赛"提前 3-7 天病害预警"与"≥2 个核心创新点"评审指标

## 一、总体架构

```
传感器/UI 气象 ──┐
PCR 巡检观测 ────┤
                 ▼
┌─────────────────────────────────────────────┐
│ assimilation.ts  贝叶斯源项估计（SIR 粒子滤波）│  ← 创新点②：数字孪生闭环
│   前向模型 = 解析高斯烟羽（同族稳态极限）        │
└──────────────┬──────────────────────────────┘
               ▼ 源位置/强度后验（含不确定椭圆）
┌─────────────────────────────────────────────┐
│ inspection-engine.runForecast  欧拉物理引擎    │  ← 创新点①：文献参数化物理模型
│   风序列驱动 · 源播种 · 平流-扩散-沉降-再释放    │
└──────────────┬──────────────────────────────┘
               ▼ 浓度场 ForecastResult
┌─────────────────────────────────────────────┐
│ infection.ts  侵染窗口 × 剂量 × 潜育期          │  → "提前3-7天发病概率"硬指标
├─────────────────────────────────────────────┤
│ ab-compare.ts  高斯烟羽 A/B 对照（差异度佐证）   │  → 差异度≥30% 实验证据
└─────────────────────────────────────────────┘
统一入口：engine.runDispersionForecast()
```

## 二、模块清单

| 文件 | 职责 |
|---|---|
| `types.ts` | 全部共享接口（编译期擦除，无运行时依赖） |
| `rng.ts` | mulberry32 种子随机数 + Box-Muller 正态采样（结果完全可复现） |
| `parameters.ts` | DEFAULT_SPORE_FATE 命运参数表、INFECTION_WINDOWS 8 病害侵染窗口表（全部带文献引用）、ALERT_THRESHOLDS、computeFateRates |
| `wind.ts` | 风场时序插值（最短角路径）、旧版摆动公式（缺省路径逐位兼容）、日变化气象合成 |
| `assimilation.ts` | extractObservations + estimateSource（粒子滤波源项反演） |
| `ab-compare.ts` | buildPlumeField（复活 gaussianPlume 的对照场）+ compareModels（log10 RMSE/偏差） |
| `infection.ts` | infectionWindowSatisfied + onsetProbability + computeInfectionRisk |
| `engine.ts` / `index.ts` | runDispersionForecast 编排入口 + 桶导出 |

## 三、关键方法学

### 3.1 贝叶斯源项估计（assimilation.ts）

- **状态** θ = [x, y, log₁₀q]：对数强度保证正值，先验取对数正态。
- **前向模型**：解析高斯烟羽（闭式）。选择依据：与欧拉引擎同属高斯扩散族（稳态极限），后验自洽；2000 粒子 × N 观测 < 50ms（完整欧拉引擎进滤波器需数十秒，不可行；格林函数卷积因生长项非线性而数学上不成立）。
- **似然**：log₁₀ 空间高斯，σ_obs = 0.3 数量级（对应 PCR 约 2 倍定量误差）；doubtful 质量观测 σ ×2。
- **静态单批后验**：一次重要性加权 + 加权矩，不做无运动重采样（静态参数重采样只损失多样性；Doucet & Johansen 2011）。N_eff 作为置信度诊断。
- **守卫**：有效观测 < 2 → 跳过同化（单观测径向退化）；2-3 观测 → 置信度 low。
- **验证**：合成源回收测试，50 个种子 ≥90% 命中（位置 ≤20m，强度 ≤0.5 数量级）。

### 3.2 欧拉引擎微升级（inspection-engine.runForecast）

- 可选 `options.windSeries`：真实风时序（线性插值 + 最短角路径），缺省时与旧版正弦摆动**逐位一致**（回归锁 ≤1e-9 相对误差，含日间+降雨与夜间稳定度 F 两场景）。
- `options.source`：在融合基准场上叠加源位置高斯播种，播种量级取同族解析烟羽近源值（模型一致性）。
- `options.fate`：命运参数表驱动 computeFateRates，替换全部手工常数；默认值即旧基线（唯一 ulp 级偏差：rainWashout 由 `/35` 改 `×(1/35)`，已在回归测试容差中锁定）。

### 3.3 侵染窗口耦合（infection.ts）

侵染概率 = f(剂量) × 1[侵染窗口满足]：

- 窗口判定：预报期内"适温 ∧ 湿度≥阈值 ∧ 叶面湿润"累计小时数 ≥ dewHoursMin（日变化气象序列由 buildDiurnalWeather 合成，夜间结露底值 0.45）。
- 剂量-响应：p = 1 − exp(−D/5000)，5000 copies/m³（critical 阈值）对应约 63%。
- 输出逐格发病概率场 + 潜育期偏移（显症时间 ≈ 预报期 + latentPeriodDays），直接支撑"提前 3-7 天预警"。

### 3.4 A/B 对照协议（ab-compare.ts）

同源、同风、同参数下，在 PCR 观测点处计算 log₁₀ 空间 RMSE 与偏差：
- 高斯烟羽（复活的 gaussianPlume，稳态解）vs 物理引擎（源播种欧拉）vs PCR 实测；
- UI"模型对照"区可切换地图渲染并查看逐期量化表；离线版实验见 python-pipeline（其 ab_results.json 显示各预报期欧拉 RMSE 0.68 稳定优于烟羽 0.93-0.95）。

## 四、参数引用表（摘录）

| 参数 | 值 | 引用 |
|---|---|---|
| 小麦条锈病窗口 | 8-16°C(适12)/湿润≥6h/RH80/潜育14d | Chen X. 2005, Plant Disease 89:992-1015 |
| 小麦赤霉病窗口 | 15-30°C(适25)/≥12h/RH85/7d | Parry et al. 1995, Plant Pathology 44:207-238 |
| 苹果黑星病窗口 | 6-24°C(适18)/≥9h/RH90/10d | MacHardy 1996, APS Press（Mills 表） |
| 葡萄霜霉病窗口 | 15-25°C(适22)/≥4h/RH95/6d | Gessler et al. 2011, Phytopathol. Mediterr. 50:3-44 |
| 其余 4 病害 | 见 parameters.ts | Agrios 2005；White 1999；Jones & Aldwinckle 1990 |
| 孢子命运默认值 | 与 v0 引擎基线一致 | Aylor & Flesch 2001；Maddison & Manners 1972；Nicholson 1993（语义解释），基线回归锁定 |

> 引用核实规则：所有 citation 字段必填；无法核实原始文献处 year=0 并在报告中注明，不编造。

## 五、测试与验证

```bash
npm run test:engine   # 16 项测试：回归锁(3) + 模块测试(13)
npx tsc --noEmit      # strict 无错（db/、worker/ 两处为模板遗留，与引擎无关）
npm run lint          # 引擎与 UI 零告警（仅 2 个先于本次改动即存在的警告）
npm run build         # 构建通过
```

UI 端到端（Playwright）：规划→全检→模拟PCR→预测 全流程 9 项检查通过、零控制台错误，
覆盖源项面板/侵染面板/A/B 对照弹窗/地图烟羽切换渲染。

## 六、离线 Python 管线（python-pipeline/）

```bash
cd python-pipeline && uv sync && uv run python scripts/run_all.py
```

产出 `artifacts/`：fate_params.json（标定参数）、infection_windows.json（窗口表）、
ab_results.json（A/B 实验）+ 3 张报告图。UI 不依赖该管线（TS 内置默认表为运行时真源）。

## 七、已知边界

- 源项反演需要 ≥2 个空间分布有效的观测；近均匀浓度场（无主导源）会得到低置信度宽椭圆——这是逆问题的诚实行为，UI 明示置信度。
- 风场时序目前由 UI/传感器导入；未接自动气象站前使用日变化合成风。
- simulation 模式下模拟 PCR 数据满足演示链路，比赛实测数据接入后无需改代码（数据层接口不变）。

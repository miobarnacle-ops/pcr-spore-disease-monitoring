# Python 软著与 Web 控制台功能对照审计

> 审计日期：2026-08-30  
> 功能基准：`揭榜挂帅.zip/软著/main_inspection_system_v4_compliance.py`  
> Web 实现基线：`spore-monitor-web` 提交 `dd6b6dc`  
> 审计方法：源码函数/界面入口对照、导出路径检查与本地自动化回归；未连接实机。

## 结论

本地 Web 控制台以 Python V4 合规版为起点，承担后续控制台整合和能力演进。原有的路径规划、田间检测、PCR 分析和基础扩散预警流程均有对应实现与界面入口；但 Web 不以逐行翻译或完全同行为目标。它以 TypeScript 重构计算核心，并可在不破坏已确认业务语义与冻结接口的前提下新增路线任务导出、机器人监控、SLAM 地图导入、浏览器数据层、病害图像识别和扩散引擎 v2 等能力。

“已对照”表示功能路径和主要输入/输出已在源码中找到；不表示结果必须与 Python 对每一组输入数值完全一致。W2 只对明确继承的核心算法、导出字段和冻结接口建立兼容性回归，并将经确认的 Web 增强行为单独固化为新基线。

## 对照范围与证据

| Python 模块 | 主要职责 | Web 对应 |
|---|---|---|
| `main_inspection_system_v4_compliance.py` | V4 综合界面与共享算法 | `app/page.tsx`、`lib/inspection-engine.ts` |
| `agri_path_planner.py` | 边界标定、覆盖选点、路线优化和导出 | `lib/inspection-engine.ts`、`app/page.tsx` |
| `field_sensing.py` | 浊度模拟、风险判级、逐点/全检和 CSV | `lib/inspection-engine.ts`、`app/page.tsx` |
| `spore_forecast.py` | 稳定度、Gaussian plume、3/5/7 天预报和报表 | `lib/inspection-engine.ts`、`lib/dispersion/*`、`app/page.tsx` |

Python 参考源的内容哈希及本地回归结果见根目录 [`远程无实机基线清单.md`](../../远程无实机基线清单.md)。

## 功能映射

| 功能域 | Python 基准能力 | Web 对应位置 | 状态 | 审计说明 |
|---|---|---|---|---|
| 底图与边界 | 导入底图、点击边界、闭合/撤销、缩放/平移 | `app/page.tsx` 的规划面板与画布处理 | 已对照 | 支持影像与 SLAM PGM/YAML 导入；保留浏览器交互方式。 |
| 参数与预设 | 参数解析、原始预设、自定义保存/导入 | `PARAMETER_PRESETS`、`savePreset`、`importPreset` | 已对照 | 自定义预设由 `localStorage` 保存。 |
| 覆盖选点 | 旋转坐标、扫描线候选池、覆盖格网、贪心选点 | `rotatePoint`、`scanlineIntersections`、`CoverageEvaluator`、`solvePlanning` | 已对照 | TypeScript 实现保留相同算法阶段；W2 需验证数值等价。 |
| 路线优化 | 地头绕行、最近邻初始路线、2-opt、里程/时间统计 | `headlandPath`、`nearestNeighbor`、`twoOpt`、`solvePlanning` | 已对照 | Web 规划结果可导出报告、JSON 和任务路线。 |
| 田间检测 | 浊度模拟、阈值判级、单点/顺序全检、重置、CSV | `simulateTurbidity`、`classifyRisk` 和环境监测面板 | 已对照 | 目前是本地模拟读数；未声称为真实传感器接入。 |
| PCR 定量 | 靶基因、Ct/浓度换算、质量标记、判定、批量模拟 | `TARGET_GENE_DATABASE`、`ctToConcentration`、`pcrVerdict`、`simulatePcr` | 已对照 | CSV、TXT、GeoJSON 与统计入口均存在。 |
| 粗精融合 | PCR 与粗检测融合热力图、相关性比较 | `buildFusionField`、`pearsonComparison` | 已对照 | 作为 V4 后续预报输入。 |
| 基础预报 | 稳定度、Gaussian plume、3/5/7 天浓度与风险输出 | `classifyStability`、`gaussianPlume`、`runForecast` | 已对照 | 保留基础兼容预报入口；已有回归测试覆盖旧实现一致性。 |
| 导出与会话 | JSON/TXT/CSV/批量导出、会话保存恢复 | `app/page.tsx` 的各导出函数、`saveSession`/`restoreSession` | 已对照 | 浏览器下载与本地存储替代 Tkinter 对话框/SQLite。 |
| 历史项目 | 保存、恢复、删除巡检项目 | `saveProject`、`loadProject`、`deleteProject` | 已对照 | 使用浏览器 `localStorage`；尚无多人/服务端同步。 |

## Web 增量能力（不计为 Python 原始功能）

| 增量 | 位置 | 当前边界 |
|---|---|---|
| 车辆可消费路线 | `lib/route-schema.ts` | 生成并校验 `schema_version: "1.0"` 的 `field/local_enu` 米制任务；已由跨仓库测试验证能被 Python 车端解析。 |
| 机器人监控与回放 | `lib/robot-bridge.ts`、`lib/use-robot-bridge.ts`、`components/robot-monitor-panel.tsx` | 本地 rosbridge/模拟数据接口与轨迹、雷达、诊断展示；本阶段未连实机。 |
| SLAM 地图读取 | `lib/slam-map.ts` | 本地 PGM/YAML 解析与渲染。 |
| 数据源抽象 | `lib/data-source.ts` | 当前为 `localStorage` 模拟数据源；真实 ROS/HTTP 源尚未接入。 |
| 扩散引擎 v2 | `lib/dispersion/*` | 粒子滤波源项估计、时变风场、物理扩散、感染风险和 A/B 对照；为 Web 增强，需独立维护参数与证据。 |
| 病害识别与监管 | `lib/disease-monitoring.ts`、`app/page.tsx` | Web 增量模块，不应倒填为软著基准已验证能力。 |

## 已识别差异与 W2 验证项

1. 规划、PCR、融合与基础预测属于“算法阶段对齐”。后续使用固定输入夹具验证关键业务语义、必要字段和容许误差；只要已声明为增强模式，就不要求与 Python 数值或流程完全一致。
2. Python 使用 Tkinter、文件对话框和 SQLite；Web 使用浏览器画布、下载和 `localStorage`。两者的交互/持久化机制不同，但业务目标对应。
3. Web 的扩散引擎 v2、机器人监控、SLAM、病害识别和监管页为新增能力，不能用 Python 软著作为它们的实测或科学有效性证据。
4. `route_v1.json` 是文件名约定，冻结的数据字段版本是 `schema_version: "1.0"`；总基线 D1 与两端实现应在下一轮接口契约文档中同步这一表述。
5. 本审计未覆盖真实传感器、rosbridge 连接、车辆执行、定位精度或田间效果；这些必须在有实机和原始数据时另行记录。

## W2 完成记录（2026-08-30）

- 新增 `tests/fixtures/soft-copyright/v4-core-compatibility.json`：以冻结哈希绑定几何、风险、稳定度、PCR 与 Pearson 样例。
- 新增 `npm run test:parity`：9 项测试覆盖继承语义、Web 重心修正、扩散模型边界、规划/预报结构、Ct 离群规则及空数据、极小地块、自交边界、重复点、非法值和非正参数。
- 将 Ct 离群检测从页面内联逻辑下沉至 `detectCtOutliers`，使 `|Z| > 2.5` 规则可复用、可测试。
- 不将 Python 的随机模拟输出、旧重心缺陷或旧 Gaussian plume 数值作为 Web 的强制目标；这些差异已在 `WEB_ENHANCEMENT_BOUNDARIES.md` 中明确。

## 本次可复现验证

- `npm run lint`：通过。
- `npx tsc --noEmit`：通过。
- `npm run test:engine`：16/16 通过。
- `npm run test:route`：4/4 通过，包括 Web 导出由车端解析器接收。
- `npm test`：构建通过，2/2 服务端渲染检查通过。

后续整合应以本审计确认的 `spore-monitor-web` 为基础：保留软著来源可追溯性、补齐需要的接口和闭环能力，并允许形成独立于 Python 的 Web 演进基线；不使用已废弃的旧“穗巡”空壳平台。

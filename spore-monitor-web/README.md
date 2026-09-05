# 多模态农田孢子监测与病害扩散预警系统 V4.0 - Web 控制台

本项目以 `main_inspection_system_v4_compliance.py` 为功能基准，将原 Tkinter 桌面程序迁移为本地浏览器控制台。

## 本地运行

```powershell
npm install
npm run dev
```

浏览器打开：<http://localhost:3000>

网站在本机运行，不需要 ChatGPT 登录，也不会自动上传或公开发布数据。

## 使用顺序

1. 路径规划：导入底图（可选），点击“标定不规则边界”，在画布上依次点击顶点，闭合边界并运行规划。
2. 田间检测：在地图或表格选择采样点，可单点读取或顺序全检。
3. PCR 分析：选择样本录入 Ct，也可导入 CSV 或批量生成模拟数据；之后生成融合热力图和对比分析。
4. 趋势预警：加载 PCR 源点，设置气象、环境与表型参数，运行 3/5/7 天预测。
5. 使用各页按钮导出 JSON、CSV、TXT、GeoJSON 或 HTML 报告。

鼠标滚轮缩放地图，按住 Shift 加左键拖拽平移，右键可在边界标定过程中撤销顶点。

完整迁移清单见 [FUNCTION_PARITY.md](./FUNCTION_PARITY.md)。

## 真实车辆 rosbridge

树莓派服务默认在 `ws://<VEHICLE_HOST>:9091` 提供 rosbridge。控制台的“机器人监控”页
仍需用户显式点击“连接机器人”，默认运动控制保持锁定；如部署地址不同，可在构建前
设置 `NEXT_PUBLIC_ROSBRIDGE_URL` 覆盖默认地址。实时位姿优先使用
`/odometry/filtered`，在 EKF 不可用时回退到 `/odom`。统一任务与遥测面板可切换到
`rosbridge` 数据源：它会接收 `/mission/status`、可选 `/gps/status` 以及上述基础遥测，
并把车端原生状态转换为 Web 契约；未启动路线任务时显示 `idle`，未接入采样器/视频时明确
显示不可用或占位。该适配仍是只读，不替代物理急停。

## 扩散预测引擎（v2.0）

趋势预警页已升级为"贝叶斯源项同化 + 物理引擎预报 + 侵染窗口耦合"三层架构：
粒子滤波从 PCR 实测反演疑似侵染源（含不确定度），欧拉引擎做风序列驱动的 3/5/7 天浓度预报，
侵染窗口/潜育期模型输出逐格发病概率，并内置经典高斯烟羽 A/B 对照（差异度佐证）。
方法学、参数引用与测试见 [ENGINE.md](./ENGINE.md)；离线标定与报告图管线见 [python-pipeline/](./python-pipeline/)。
引擎测试：`npm run test:engine`。

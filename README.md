# PCR / Spore Patrol Project

这是 PCR 孢子病害监测机器人项目的公开统一仓库，汇总车辆导航、Web 控制台、离线算法、测试证据、仿真材料、硬件资料和汇报材料。

## 目录

| 路径 | 内容 |
|---|---|
| `spore-monitor-web/` | Next.js/React Web 控制台、Mock/Replay/rosbridge 数据链路、路线导出、契约与回归测试 |
| `spore-vehicle-nav/` | ROS 2 车辆端：底盘串口、YDLIDAR、GNSS/ENU、EKF/SLAM、路线跟踪与采样状态机 |
| `spore-patrol-robot/` | 早期车辆/仿真基线与串口测试材料 |
| `spore-patrol-robot-feature-lidar/` | 雷达/SLAM 特性分支及仿真结果归档 |
| `轮趣R550 PLUS/` | 底盘、控制板、雷达和烧录资料；媒体/大压缩包由 LFS 管理 |
| `pcr_progress_sync_ppt/`、`gnss_progress_sync_ppt/` | 项目进度同步用 PPTD/PPTX 工程 |
| `legacy-materials/` | 从历史总归档提取并脱敏后的可公开源码、报告和资料 |
| `multiplatform-showcase/` | “穗巡”多端离线展示应用：Vite/React、Windows Electron、Android Capacitor、验收记录与发行包 |
| `报告书撰写详细计划_三模块_2026-09-06.md`、`报告书三模块初稿_*.md` | 三模块报告写作基线、初稿、润色稿和自我审计记录 |
| `report_assets/` | 报告图表、公式图、成员材料摘录和可复现的制图脚本 |
| `spore-vehicle-nav/results/` | 单垄仿真与真实建图的精选地图、对比图和报告使用说明；原始录包不随源码默认下载 |

## 克隆

```bash
git lfs install
git clone https://github.com/miobarnacle-ops/pcr-spore-disease-monitoring.git
cd pcr-spore-disease-monitoring
git lfs pull
```

只查看源码和文档时可以不下载 LFS 大文件；需要硬件视频或供应商归档时再执行 `git lfs pull`。

## 最小可复现环境

### Web 控制台

要求 Node.js `>=22.13.0`。

```bash
cd spore-monitor-web
npm ci
npm run dev
```

常用检查：

```bash
npm run lint
npx tsc --noEmit
npm run test:engine
npm run test:contracts
npm run test:data-bus
npm run test:route
npm test
```

默认开发模式使用 Mock 数据，不会向真实车辆发布 `/cmd_vel`。

### 离线算法

要求 Python `>=3.11` 和 `uv`：

```bash
cd spore-monitor-web/python-pipeline
uv sync
uv run python scripts/run_all.py
```

### 车辆端离线验证

```bash
cd spore-vehicle-nav
./verify.sh
```

### ROS 2 / 实车

推荐目标为 Raspberry Pi 5（8 GB）+ Ubuntu Server 24.04.4 arm64 主机 + Docker `ros:humble-ros-base`。工作区挂载到容器 `/ws` 后再构建。真实底盘、雷达、GNSS、串口、供电、网络、急停和现场场地不可能通过 Git clone 自动获得。

## 安全边界

- 公开仓库不包含真实网络密码、SSH 私钥、设备密码、访问令牌或内部地址。
- 私密车辆交接和实机运行参数由项目负责人通过安全信道单独提供。
- `node_modules`、`.next`、ROS `build/install/log`、Python 虚拟环境和缓存不上传。
- 运行任何会让车辆运动的命令前，必须有人在车旁、急停可用、车轮/路线状态已确认；软件停车不等于物理急停。

## 验证边界

报告中要区分离线测试、Mock/Replay、Gazebo 仿真、树莓派静止链路、小尺度实车路线和正式场地/精度/采样联动验证。公开仓库保留证据材料，但不把仿真或离线通过写成比赛级实车结论。

详见 `docs/RUNTIME_ENVIRONMENT_PUBLIC.md`、`docs/PUBLIC_UPLOAD_SCOPE.md`、`docs/INCREMENTAL_SYNC_2026-09-07.md`、`docs/INCREMENTAL_SYNC_2026-09-13.md` 和 `spore-vehicle-nav/HANDOVER_PUBLIC.md`。

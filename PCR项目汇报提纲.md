# PCR 项目组内进度同步

> 用途：组内成员同步当前开发进度、技术实现、测试证据和待办事项。  
> 信息截止：2026-09-05

## 1. 当前总体状态

项目目前由四条主线组成：

1. 车辆硬件与 ROS 车辆端：底盘、雷达、EKF、SLAM、路线跟踪和 GNSS。
2. Web 控制台：地块规划、环境感知、PCR、病害、预测、告警和机器人监控。
3. 算法与数据：Python 软著参考源码、PCR 处理、孢子扩散和感染风险预测。
4. 集成与验证：Web—车辆契约、rosbridge、Mock/Replay、测试日志和实机证据。

当前工程基线：

- spore-vehicle-nav：当前车辆侧主仓库，main 分支，最新同步提交为 2026-09-04。
- spore-monitor-web：当前 Web 主工程，最新整合代码已经可以构建，但工作区仍有未提交和未跟踪文件。
- spore-patrol-robot：早期底盘 ROS 基础仓库，主要作为历史参考。
- spore-patrol-robot-feature-lidar：旧的雷达/SLAM 功能快照，当前车辆开发成果已同步到 spore-vehicle-nav。

总体判断：代码和离线验证已经比较完整，车辆基础栈和小尺度路线已有实机结果；RTK、正式场地、真实采样/PCR、独立真值和安全 failsafe 仍未闭环。

## 2. 车辆底盘与部署

### 已完成

- 硬件：WHEELTEC R550 PLUS 四驱底盘、C50C STM32、树莓派 5、X3 Pro 雷达。
- STM32 通信协议：11 字节速度控制帧、24 字节反馈帧，反馈频率约 20 Hz。
- ROS 2 底盘驱动已发布：
  - /cmd_vel
  - /odom
  - /imu/data_raw
  - /battery_state
  - /diagnostics
  - TF
- ROS 驱动层配置 cmd_vel_timeout_s=0.30，控制输入过期时输出零速度。
- 树莓派实际采用 Ubuntu Server 24.04.4 + Docker ROS 2 Humble，工作区和 YDLIDAR SDK 已完成部署。
- 已增加 spore-vehicle-stack.service、spore-rosbridge.service、统一 full_stack.launch.py，以及容器重启和重复节点清理。

### 实测结果

- 夜间架空自动测试：8 小时、48 轮通过。
- 2026-08-30 实机静止接入：底盘、IMU、融合里程计、雷达、电池、诊断和 TF 数据正常。
- 静止状态频率约为：融合里程计 20 Hz，雷达 11.3 Hz。

### 当前问题

- STM32 固件 failsafe 失联停车复测为 1.309 s / 1.409 s，超过 1.2 s 目标。
- 车轮最终能够停下，但底层响应时间仍不满足严格验收要求。
- 物理急停、低速运动安全、现场断联停车仍需单独验证。

## 3. 雷达、定位与 SLAM

### 技术实现

- X3 Pro 已完成 ROS 2 驱动、/dev/ydlidar 设备映射、雷达方向修正、RViz 配置和 SensorDataQoS 订阅。
- 实测 /scan 约 11–12 Hz，雷达方向参数已修正为 reversion=true、inverted=true。
- EKF 使用轮速和 ICM20948 IMU，输出 /odometry/filtered。
- TF 约定为：map → odom → base_footprint → base_link → laser_link。
- SLAM 使用 SLAM Toolbox；SLAM 负责 map → odom，EKF 负责 odom → base_footprint。

### 仿真结果

- 已实际运行 ROS 2 Humble + Gazebo Classic + SLAM Toolbox。
- canonical 模拟农田参数：8 m × 6 m、3 条模拟垄、1.20 m 净通道、1.60 m 地头、0.05 m 栅格。
- 9 个航点固定低速闭环通过。
- 地图、PGM/YAML、pose graph/data 均已保存。
- 两次同配置仿真地图重复比较通过，垄中心最大偏移 0.050 m，比较门槛为 0.150 m。

### 实机结果

- 2026-08-26：树莓派底盘 + 雷达 + EKF + SLAM 组合栈运行。
- 2026-09-01：单垄场地建图和 U 形掉头成功。
  - 自主行驶约 1.73 m；
  - U 形掉头行驶约 3.36 m；
  - 航向漂移约 0.2°；
  - PGM/YAML 和 pose graph/data 已保存。

### 尚未完成

- 学校小花园正式建图和正式路线。
- 实机重复路线 rosbag 和统计结果。
- 独立真值对比、定位误差 P95 和最大误差。
- 室外强光、植被环境下的雷达长期稳定性。
- RTK 与 SLAM 的全局融合。

## 4. 路线规划、路径跟踪与任务状态机

### 接口和算法

- Web 与车辆共用 route_v1.json：
  - schema_version=1.0；
  - frame_id=field；
  - coordinate_type=local_enu；
  - 单位为米；
  - 地块边界、采样点和路径使用同一米制坐标。
- 航点字段包括：seq、x_m、y_m、yaw_rad、type、round、sample_id、speed_limit_mps、tolerance_m。
- 车辆端已实现：
  - 路线解析和几何校验；
  - field→map/odom 坐标转换；
  - 路径平滑和重采样；
  - Pure Pursuit 跟踪；
  - 采样点状态机；
  - 暂停、继续、返航、取消和故障转移；
  - 雷达前向 ±90° 障碍检测；
  - 里程计/雷达超时停车；
  - 10 Hz /cmd_vel 和 1 Hz /mission/status 心跳。

### 实车验证

小尺度已记录 6 类、9 次通过：

- 1 m 直线；
- 3 m 直线 ×3；
- 方形回环；
- 双垄往复 ×2；
- 完整多点采样路线；
- 静态障碍停车。

### 当前边界

- 小尺度测试证明了基础路线跟踪和任务状态机能力，但还没有独立真值误差。
- 状态机中的 2 秒采样驻留目前是模拟行为，不代表真实采样器已经接入。
- 尚未完成 Nav2 全流程、动态避障、正式覆盖率和小花园完整路线。

## 5. GNSS 与 RTK

### 已完成

- ATGM336H 已完成 ROS 2 离线适配包：
  - NMEA GGA/GLL/VTG 解析；
  - /fix；
  - 速度、航向、原始数据和诊断；
  - 可选 WGS84→ENU；
  - YAML 和 launch 配置。
- 当前车辆端 GNSS 离线测试 5 项通过。

### 当前结论

- ATGM336H 是普通单频单点 GNSS，不是 RTK 接收机。
- 当前不能提供 RTK Float/Fix、RTCM 差分或双天线定向。
- 当前设备使用 /dev/ttyUSB0，而 X3 Pro 也占用该串口，专用串口和现场联调仍需处理。
- RTK 全链路尚未启动：多频接收机、测量型天线、CORS/NTRIP 或自建基站、RTCM、RTK 状态和全局融合均未完成。

因此，现阶段不能用 ATGM336H 证明“定位误差小于 0.5 m”。

## 6. Web 控制台

### 已完成功能

当前 Web 包含 7 个功能页签：

- 路径规划；
- 环境感知；
- PCR 检测；
- 病害识别；
- 趋势预测；
- 监管告警；
- 机器人监控。

具体功能包括：

- 地块边界绘制和路线生成；
- route_v1.json 导出；
- 环境点位和模拟数据；
- PCR Ct 值、浓度、质量、LOD、离群值和融合；
- 病害风险热力图；
- 3/5/7 天风险预测；
- CSV、JSON、TXT、GeoJSON 和报告导出；
- /odometry/filtered 优先、/odom 备用；
- 雷达、电池、诊断、任务状态和可选 GNSS 展示。

### 当前数据模式

- Mock：确定性任务模拟，不连接实机，不发布真实 /cmd_vel。
- Replay：读取固定回放数据，只读。
- rosbridge：读取车辆实时遥测，当前以只读适配为主。
- 持久化：主要使用浏览器 localStorage，还没有正式后端数据库和文件服务。

### 当前验证

- lint 通过；
- TypeScript 检查通过；
- Web 引擎测试 16/16；
- Python-Web 兼容性测试 9/9；
- 集成契约测试 6/6；
- 本地会话存储测试 2/2；
- Mock/Replay 数据总线测试 3/3；
- 路线测试 4/4；
- 构建和服务端渲染测试 2/2。

### 工程状态

Web 当前整合功能已经可以构建，但工作区存在已修改和未跟踪文件，主要包括任务面板、数据总线、rosbridge 适配、会话仓库和契约测试。需要后续整理后提交，形成正式发布基线。

## 7. PCR、病害识别与扩散预测

### 当前实现

- Python 软著源码作为业务语义参考，主要文件包括：
  - agri_path_planner.py；
  - field_sensing.py；
  - main_inspection_system_v4_compliance.py；
  - spore_forecast.py。
- Web 已迁移并增强：
  - PCR Ct 值到浓度和判定；
  - 质量控制、LOD、离群值和多点融合；
  - 粒子滤波源估计；
  - Euler 扩散模型；
  - Gaussian plume A/B 对比；
  - 温度、湿度、叶面湿润时间和感染窗口；
  - 3/5/7 天风险预测。
- 粒子滤波源估计至少需要两个空间观测；单点观测会降级为普通融合预测。
- 已有离线 Python 校准、A/B 实验结果和预测图表。

### 当前边界

- 当前数据主要是模拟数据、样例数据和离线实验数据。
- 病害识别目前是浏览器端颜色/纹理原型，不是完整训练模型。
- 尚未看到完整真实 PCR 实验记录、引物/探针验证、电泳图、田间样本对照和病害准确率报告。
- 因此暂不能宣称病害识别准确率达到 90%，也不能宣称已经实现真实提前 3–7 天预警。

## 8. 当前质量与证据分层

| 层级 | 当前结论 |
|---|---|
| 代码 | Web、车辆端主要功能和接口已实现 |
| 离线测试 | 车辆 91 项路线/安全测试、5 项 GNSS 测试、7 份 YAML 校验通过；Web 相关测试和构建通过 |
| 仿真 | 8 m × 6 m 模拟农田建图、路线闭环和重复地图比较通过 |
| 实机静止 | Pi、底盘、雷达、EKF、SLAM、rosbridge 静止数据链路通过 |
| 小尺度实机运动 | 6 类、9 次路线测试记录通过；单垄建图和 U 形掉头完成 |
| 正式性能验收 | RTK、独立真值、P95、正式场地路线、真实采样和病害准确率尚未完成 |

## 9. 当前主要问题

1. RTK 还没有形成设备、差分服务、天线、状态和融合的完整链路。
2. 固件 failsafe 响应时间超过 1.2 s 目标。
3. 正式小花园路线、重复测试、rosbag 和独立真值缺失。
4. 真实采样器、高清视频和环境传感器尚未接入。
5. Web 没有正式后端持久化，当前主要依赖 localStorage。
6. Web 最新整合代码尚未提交，历史仓库、雷达快照和当前主仓库之间需要继续统一说明。
7. 部分旧文档仍保留过时结论，例如 Pi 5 的旧版 22.04 原生部署流程、旧测试数量和“failsafe 已通过”的早期记录。

## 10. 下一阶段工作顺序

### P0：先补安全和正式证据

- 修复并复测固件 failsafe。
- 完成物理急停和现场低速安全流程。
- 完成多频 RTK 选型、采购、CORS/NTRIP 或基站验证。
- 在小花园完成正式地图、路线、重复运行和 rosbag。
- 建立独立真值，输出定位误差、横向误差和重复性报告。

### P1：补齐功能闭环

- 冻结采样器接口和 sample_id 数据链路。
- 完成采样—PCR—位置绑定。
- 接入环境传感器、相机和视频。
- 将 Web 数据从 localStorage 迁移到后端数据库/文件存储。
- 整理并提交 Web 当前未提交改动。

### P2：补齐比赛指标和材料

- 采集真实 PCR 和田间样本。
- 验证 5–8 种病害识别准确率。
- 验证真实 3–7 天预警效果。
- 整理完整演示视频、实验记录、报告和软著材料。

## 11. 主要证据文件

- 总体集成：<REPO_ROOT>/INTEGRATION_PLAN.md
- 车辆主审计：<REPO_ROOT>/机器人车辆导航子系统工作计划与agent协作指南.md
- 车辆代码说明：<REPO_ROOT>/spore-vehicle-nav/README.md
- 车辆更新日志：<REPO_ROOT>/spore-vehicle-nav/CHANGELOG.md
- Web 代码说明：<REPO_ROOT>/spore-monitor-web/README.md
- 仿真建图说明：<REPO_ROOT>/spore-vehicle-nav/docs/模拟农田建图测试.md
- 实机接入前置包：<REPO_ROOT>/spore-vehicle-nav/docs/实机接入前置包.md
- 夜间测试日志：<REPO_ROOT>/night_run_20260814/main.log


# 车辆导航子系统代码约定（spore-vehicle-nav）

本仓库承载机器人车辆导航子系统的**车端代码与配置**，是本人（车辆部分负责人）后续进度与成果的归集目录。
所有代码必须先通过离线单元测试，再上车部署到树莓派 `/home/pi/spore_patrol_ws` 等价工作区。

> 配套主指导文件：`../机器人车辆导航子系统工作计划与agent协作指南.md`（v0.6.0）。本仓库是其中"阶段 C（建图）"与"阶段 D（路径跟踪）"的代码落地处。

## 1. 坐标系与 TF（沿用主仓库已理顺链）

- 链：`map -> odom -> base_footprint -> base_link -> laser_link`，新增 `gnss_link`。
- SLAM 发 `map->odom`，EKF 发 `odom->base_footprint`，TF 唯一发布者规则不变。
- 田块 `field`（local_enu）与 `map` 之间为**静态变换**，由任务包起始位姿决定（见 §3）。

## 2. 任务包 schema（route_v1.json，决策 D1 已冻结）

- 顶层：`schema_version`、`frame_id: "field"`、`coordinate_type: "local_enu"`、`unit: "m"`、
  `field_polygon_m`、`sampling_points`、`path`。
- 航点字段（path 数组元素）：
  - `seq: int`
  - `x_m: float`、`y_m: float`（field 坐标系，米）
  - `yaw_rad: float | null`
  - `type: "start" | "transit" | "sampling" | "turn" | "return"`
  - `round: int`
  - `sample_id: str | null`
  - `speed_limit_mps: float`
  - `tolerance_m: float`
- 原点 = 第一个边界点；`+X` = 第一个边界边方向；`+Y` = 田块内部一侧。
- 车辆端需将 field 坐标按**实车在 map/odom 下的起始位姿**变换到 map/odom 后再跟踪。
- 权威定义见 `../spore-monitor-web/ROUTE_SCHEMA.md`。

## 3. field → map/odom 变换

- 给定实车起始位姿 `T_start`（在 map 或 odom 下的 x,y,yaw），field 坐标 (xf,yf) 转车体/map 坐标：
  - `xm = x_start + xf*cos(yaw_start) - yf*sin(yaw_start)`
  - `ym = y_start + xf*sin(yaw_start) + yf*cos(yaw_start)`
  - 朝向：若航点 `yaw_rad` 非 null，则目标 yaw = yaw_start + yaw_rad。
- 该变换为纯函数，必须放在可离线 pytest 的模块（`field_map_transform.py`），不得依赖 ROS 运行时。

## 4. 话题约定（来自 base_driver / EKF）

- 订阅（本节点输入）：
  - `/odometry/filtered`（Odometry，EKF 输出，**优先**）；回退 `/odom`。
  - `/imu/data_raw`（Imu）、`/scan`（LaserScan，供 SLAM）。
- 发布（本节点输出）：
  - `/cmd_vel`（Twist）——路径跟踪控制输出。
  - `/mission/status`（String/JSON）——任务状态机状态与采样事件。
  - `/validation/*`（调试、轨迹记录、误差统计）。
- **安全**：base_driver 自带 `cmd_vel_timeout_s = 0.30` 看门狗——本节点必须持续以 ≥5 Hz 发布 cmd_vel；
  停车时发布零速度而非停止发布，否则会触发固件失联停车（已知 FAIL：1.3~1.4 s 响应，仍比无线程安全）。

## 5. 速度 / 转弯约束（来自底盘与验证计划）

- 默认限速 0.12 m/s（采样点 `speed_limit_mps` 优先），角速度 ≤ 0.30 rad/s。
- 底盘最小转弯半径约 0.5 m；急转折航点**必须先圆弧/样条平滑 + 等距重采样**，不得直接发给底盘。
- 阶段 D 分级试验顺序（NAVIGATION_VALIDATION_PLAN Gate C/D/E）：
  1 m 直线 → 3 m 直线 → 缓弯 → 单垄+地头 U 形转弯 → 双垄往复 → 完整路线+采样点停车（停车 2 s 模拟采样）→ 静态障碍停车。
  每级至少成功 3 次再升级。

## 6. 编程语言与结构

- 节点用 Python（rclpy），与 feature-lidar 一致。
- 纯逻辑（解析 / 变换 / 控制 / 状态机）放独立模块，便于离线 pytest；ROS 节点只做 I/O 胶水。
- `spore_patrol_route_validation`：阶段 D 路径跟踪包。
- `spore_patrol_gnss`：ATGM336H NMEA→`/fix`、速度、诊断和可选 WGS84→ENU 适配包；默认关闭串口，普通定位质量标记为 `single`。
- `spore_patrol_nav_bringup`：阶段 C EKF + SLAM Toolbox 启动配置（launch/config）。

## 7. 测试

- 离线 pytest 覆盖：
  - `route_model`：解析 + 字段校验（越界/超速/缺字段拒绝）。
  - `field_map_transform`：变换数学（原点/轴向/旋转）。
  - `pure_pursuit`：收敛性、曲率约束、目标点切换。
  - `sampling_state_machine`：状态转移（ARRIVED→SETTLING→SAMPLE_REQUESTED→…）。
  - `spore_patrol_gnss`：GGA/GLL/VTG 解析、校验和、无定位、WGS84→ENU 与故障输入。
- 用 `python -m pytest tests/ -q` 可跑，无需 ROS 运行时。
- 实车/SLAM 集成测试必须在树莓派上由本人在场执行，不在此环境运行。

## 8. Git 与安全

- 不提交凭据、坐标真值、账号；`maps/`、`results/` 仅提交 `.gitkeep` 或占位。
- 公开仓库不作为默认；本地为主。

## 9. 与主仓库的关系

- 不重写现有路径规划器与底盘驱动，只做**适配层接入**。
- 本仓库代码最终在树莓派工作区 colcon build 后随车运行；此处是源码归集与离线校验地。

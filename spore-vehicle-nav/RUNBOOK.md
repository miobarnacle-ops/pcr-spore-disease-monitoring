# 上车运行手册（Stage C 建图 / Stage D 路径跟踪）

> 适用：树莓派 5（ROS 2 Humble，Docker `ros:humble-ros-base` 容器，host 网络/privileged/设备直通，工作区 `~/spore_patrol_ws`，容器内 `/ws`，`humble` 别名自动 source，`ROS_DOMAIN_ID=77`）。
> 本手册对应 `spore-vehicle-nav` 仓库的两个包：`spore_patrol_nav_bringup`（阶段 C）、`spore_patrol_route_validation`（阶段 D）。
> **所有实车动作必须先满足下方"安全红线"。**

---

## 0. 安全红线（每次上车前必读）

- **架空轮**：实车驱动前车轮必须离地；首次动车只做低速、短距、人在急停旁。
- **急停就绪**：手边有物理急停/断电手段；已知 failsafe 失联停车实测 1.3~1.4 s（超 1.2 s 阈值，判定 FAIL），只能靠限速 + 急停兜底。
- **看门狗**：base_driver 有 `cmd_vel_timeout_s = 0.30` 看门狗；任何跟踪节点必须 ≥5 Hz 持续发布 `/cmd_vel`，停车时发零速度，**不得停止发布**。
- **先只读后运动**：先确认 `/odom`、`/imu/data_raw`、`/scan`、`/odometry/filtered` 均正常再动车。
- **限速**：默认线速度 0.12 m/s（采样点 `speed_limit_mps` 优先），角速度 ≤0.30 rad/s。

---

## 1. 把代码部署到树莓派

在 PCR 开发机（或任意能连 Pi 的机器）上：

```bash
# 假设 Pi 可达（<VEHICLE_HOST> 或热点 IP，ROS_DOMAIN_ID=77）
# 方式 A：直接拷两个包进现有工作区 src（推荐，避免新建工作区）
ssh pi@<VEHICLE_HOST>
  cd ~/spore_patrol_ws/src
  # 把本仓库的 src/ 下两个包软链/拷入：
  ln -s /path/to/spore-vehicle-nav/src/spore_patrol_route_validation .
  ln -s /path/to/spore-vehicle-nav/src/spore_patrol_nav_bringup .
  cd ~/spore_patrol_ws
  source /opt/ros/humble/setup.bash   # 容器内用 humble 别名
  colcon build --symlink-install --packages-select spore_patrol_route_validation spore_patrol_nav_bringup
  source install/setup.bash
```

> 若用 Docker 容器：把 `spore-vehicle-nav` 挂载进容器 `/ws/src` 后再 build。保持 `ROS_DOMAIN_ID=77` 与底盘/雷达节点一致。

---

## 2. 阶段 C：EKF + SLAM 建图

目标：跑通"底盘 + 雷达 + EKF + SLAM Toolbox"，产出第一张室内/模拟农田地图。

### 2.1 启动

```bash
ros2 launch spore_patrol_nav_bringup ekf_slam_bringup.launch.py mapping:=true
# 该 launch 应拉起：底盘驱动（可选，默认假定已运行）、EKF（输出 /odometry/filtered）、SLAM Toolbox（发布 map->odom）
```

### 2.2 只读检查（动车前）

```bash
ros2 topic list | grep -E '/(odom|imu/data_raw|scan|odometry/filtered|map)'
ros2 topic hz /odom /imu/data_raw /scan /odometry/filtered
ros2 run tf2_tools view_frames   # 或 rviz2 看 TF：map->odom->base_footprint->base_link->laser_link
```

- `/scan` 应约 11~12 Hz、`/odom` 20 Hz、`/odometry/filtered` 正常出。
- TF 链必须唯一发布者：SLAM 发 `map->odom`，EKF 发 `odom->base_footprint`。

### 2.3 建图（架空→低速→走线）

1. 车轮架空先低速点动，确认 `/cmd_vel`→轮端响应正常、无异常。
2. 落地后人工/遥控低速绕行测试区域一圈，观察 RViz 中地图增长、无严重重影。
3. 保存地图：

```bash
# SLAM Toolbox 保存（具体服务名以实际配置为准）
ros2 service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap "{name: {data: '/home/pi/spore_patrol_ws/maps/spore_field_map'}}"
# 或用 maps/ 目录：把 pgm/yaml 放到 spore-vehicle-nav/maps/ 并提交占位说明
```

### 2.4 阶段 C 验收判据

- 室内与（后续）模拟农田均有可用地图；`map->odom->base_footprint` 连续唯一；
- 短时扫描退化时里程计连续；地图回环无明显重影。
- 保存地图至 `maps/`，记录 rosbag 至 `results/`。

---

## 3. 阶段 D：route_v1.json 路径跟踪

目标：把 Web 导出的 `route_v1.json` 转为实车可执行路径并闭环跟踪 + 采样点停车。

### 3.1 准备任务包

- 从 Web 控制台"路径规划"页导出 `route_v1.json`（schema 见 `../spore-monitor-web/ROUTE_SCHEMA.md`）；
- 记录**实车起始位姿**：把小车放在田块第一个边界点附近，朝向 = 第一个边界边方向，得到 `start_pose_x/y/yaw`（米 + 弧度，map/odom 系）。

### 3.2 启动跟踪节点

```bash
ros2 launch spore_patrol_route_validation route_tracker.launch.py \
  route_file:=/path/to/route_v1.json \
  start_pose_x:=0.0 start_pose_y:=0.0 start_pose_yaw:=0.0 \
  odom_topic:=/odometry/filtered cmd_vel_topic:=/cmd_vel \
  max_linear_mps:=0.12 max_angular_radps:=0.30 lookahead_m:=0.3
```

- 节点会：解析并校验 JSON → field→map 变换 → 平滑/重采样（最小转弯半径 0.5 m）→ Pure Pursuit → 发布 `/cmd_vel`；到 `sampling` 航点停车 2 s 并发布 `/mission/status`。
- 先**空载/架空**跑一遍，确认无目标点跳变、无曲率违规，再落地。

### 3.3 分级试验（每级 ≥3 次成功再升级）

1. 1 m 直线往返
2. 3 m 直线
3. 缓弯
4. 单垄 + 地头 U 形转弯
5. 双垄往复
6. 完整牛耕式路线 + 采样点停车（停车 2 s 模拟采样）
7. 静态障碍停车（雷达近距触发）

每次录包：`ros2 bag record -a -o results/run_$(date +%Y%m%d_%H%M%S)`。

### 3.4 阶段 D 验收判据（模拟场地阶段目标）

- 路线完成率 ≥80%、采样点到达率 ≥90%；
- 横向跟踪误差 P95 ≤0.20 m（规划线 vs 实驶轨迹，用独立真值或高精度回放对比）；
- 全程录包 + 固定机位视频可追溯。

---

## 4. 故障排查速查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 话题互相看不见 | `ROS_DOMAIN_ID` 不一致 / 校园 WiFi 禁组播 | 统一 `ROS_DOMAIN_ID=77`；改手机热点或网线；必要时 CycloneDDS 静态对端 |
| `/odom` 无数据 | 底盘串口/udev | 查 `/dev/ttyACM0`、dialout 组、`ros2 topic echo /odom` |
| `/scan` 无 | 雷达 udev/权限 | 查 `/dev/ydlidar`、CP210x 驱动、`ros2 topic echo /scan` |
| 小车不动 / 急停 | `cmd_vel` 未持续发布 | 确认节点 ≥5 Hz 发 `/cmd_vel`；查 base_driver 看门狗日志 |
| 建图重影严重 | 初始位姿/IMU 标定 | 检查 EKF 协方差、IMU bias；先静态对准 |
| 失联停车偏慢 | 已知固件 FAIL | 限速运行 + 急停兜底，不依赖自动失联停车 |

---

## 5. 记录与回传（每次实车后）

- 录包、轨迹、误差统计、视频放入 `results/`（不提交敏感信息）；
- 把本次日期、场地、参数、成败填回主计划 `机器人车辆导航子系统工作计划与agent协作指南.md` 的 §11.1 与 §15；
- 真值优先：车顶 ArUco + 高处相机单应性，或卷尺基准点 + 俯视视频人工复核；**禁止只用自身定位评估自身精度**。

---

## 6. 遗留待办（非本手册范围）

- RTK 阶段 E：最迟 09-03 启动选型采购，否则定位 <0.5 m 指标无实测证据；
- 采样器联动阶段 F：接口冻结后用模拟节点先跑状态机，再接真实设备；
- failsafe 失联停车仍 FAIL：固件 D50A 超时机制未排查，列为已知风险。

---

## 7. 小花园一次性作战清单（场地不可过夜版）

> 场地无法连续保留道具 → 一场session内完成建图+验证+取证。总净时 ~3h，预留半天。

| # | 阶段 | 执行者 | 时间 |
|---|---|---|---|
| 0 | 场外预备（裁板/装袋/编号） | 人 | 前一夜 |
| 1 | 运输到场 | 人 | 20m |
| 2 | 上电+栈检查（odom/scan/EKF/SLAM） | agent远程 | 15m |
| 3 | 拉线放样（2~3垄+地头+采样点） | 人量agent报数 | 30m |
| 4 | 立垄固定+地面贴标记 | 人 | 30m |
| 5 | 静态雷达验证（scan_probe：垄可见+前向min≥0.6m） | agent | 10m |
| 6 | 低速绕场建图+图质检 | 人推agent监控 | 20m |
| 7 | save_slam_map.sh 双保存 + scp回传 | agent | 10m |
| 8 | 实测几何→route_v1.json 现场生成部署 | 人量agent生成 | 20m |
| 9 | 首跑完整牛耕+录包 | agent控车 | 10m |
| 10 | 复跑×2 + 障碍停车演示 | agent控车 | 15m |
| 11 | 证据固化（bag/视频/日志→本地→push） | agent | 20m |
| 12 | 拆收复原 | 人 | 20m |

**止损**：图差→补扫一次（+10m）；再差→降级用可用图+双垄路线取证。
**纪律**：步骤7完成后任何道具不得移动；垄高20–25cm（雷达面z=0.254m）；通道宽1.2m（>0.5m障碍阈值+余量）。

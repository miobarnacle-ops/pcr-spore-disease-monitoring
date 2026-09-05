# 公开运行环境说明

本文档只描述可公开复现的环境和占位配置，不包含真实账号、密码、内部 IP 或设备凭据。实际联调参数由项目负责人单独发送。

## 环境分层

| 层级 | 推荐环境 | 用途 |
|---|---|---|
| Web | Node.js >=22.13.0、npm、现代浏览器 | 控制台、路线规划、Mock/Replay、rosbridge 适配 |
| 离线算法 | Python >=3.11、uv、NumPy、Matplotlib、Pydantic | 扩散/感染窗口/校准和图表 |
| 车辆离线逻辑 | Python 3、pytest、PyYAML | 路线、ENU 变换、Pure Pursuit、状态机、安全门 |
| ROS 2 | ROS 2 Humble、colcon、robot_localization、slam_toolbox、Nav2 map server、Gazebo Classic | 底盘、雷达、EKF、SLAM、仿真 |
| 实车主机 | Raspberry Pi 5；当前实机为 Ubuntu Server 24.04.4 arm64 + Docker `ros:humble-ros-base` | 车端运行与服务恢复 |

历史资料保留了 Ubuntu 22.04 原生 Humble 的尝试记录；当前实机以 24.04.4 主机运行 Docker Humble 为准。

## Web 与 Python

```bash
cd spore-monitor-web
npm ci
npm run dev

cd python-pipeline
uv sync
uv run python scripts/run_all.py
```

Web 依赖由 `package-lock.json` 固定，Python 依赖由 `pyproject.toml` 和 `uv.lock` 固定。

## ROS 2 车端

```bash
source /opt/ros/humble/setup.bash
cd /ws
colcon build --symlink-install
source install/setup.bash
```

公开占位：

| 设备 | 占位 | 说明 |
|---|---|---|
| C50C 底盘 | `<CHASSIS_SERIAL>`，常见 `/dev/ttyACM0` | 依赖 USB 枚举和 udev |
| YDLIDAR X3 Pro | `<LIDAR_SERIAL>`，建议 `/dev/ydlidar` | 依赖 CP210x 和设备权限 |
| ATGM336H | `<GNSS_SERIAL>` | 必须确认专用设备，不能误读雷达端口 |
| rosbridge | `ws://<VEHICLE_HOST>:9091` | 实际地址不入库 |

关键话题：`/odom`、`/imu/data_raw`、`/odometry/filtered`、`/scan`、`/cmd_vel`、`/mission/status`、`/fix`。目标频率和消息契约见车端文档。

## 现场顺序

1. 急停、供电、车轮、障碍和观察人确认；
2. 只读检查反馈、TF、雷达和诊断，不发布非零 `/cmd_vel`；
3. 通过安全评审后进行架空低速和分级路线测试；
4. 任何正式精度结论都要绑定日志、地图、rosbag 或独立真值。

公开仓库可以复现 Web、离线算法、Mock/Replay、车辆纯逻辑、ROS 源码构建和仿真；不能仅靠 clone 获得树莓派、底盘、雷达、GNSS、采样器、相机、现场网络和实车性能证据。


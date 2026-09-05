# spore-vehicle-nav

机器人车辆导航子系统**车端代码与配置**归集仓库（ROS 2 Humble，Python/rclpy）。

本仓库对应主计划 `../机器人车辆导航子系统工作计划与agent协作指南.md` 的：

- **阶段 C（EKF + SLAM 建图）**：`spore_patrol_nav_bringup/` —— robot_localization EKF 与 SLAM Toolbox 的 launch/config。
- **阶段 D（route_v1.json 接入 + Pure Pursuit 路径跟踪）**：`spore_patrol_route_validation/` —— 任务包解析、field→map 变换、Pure Pursuit、采样任务状态机。
- **阶段 C 仿真建图执行说明**：[`docs/模拟农田建图测试.md`](docs/模拟农田建图测试.md) —— 本仓库内 8×6 m 场景、离线验收和 ROS 2/Gazebo 地图测试链。

## 目录

```
spore-vehicle-nav/
├── CONVENTIONS.md        # 坐标系/TF/话题/约束/测试约定（所有代码必须遵守）
├── src/
│   ├── spore_patrol_base_driver/        # C50X/STM32 串口底盘驱动
│   ├── spore_patrol_bringup/            # 底盘+雷达+机器人模型启动
│   ├── spore_patrol_description/        # URDF、RViz 和模型资源
│   ├── spore_patrol_lidar/              # X3 Pro 参数与启动
│   ├── spore_patrol_sim/                # Gazebo 模拟农田与仿真 SLAM 参数
│   ├── ydlidar_ros2_driver/             # YDLIDAR ROS 2 驱动源码
│   ├── spore_patrol_route_validation/   # 阶段 D
│   └── spore_patrol_nav_bringup/       # 阶段 C
├── maps/                 # 实机/现场地图归档
├── results/              # 测试/实车/仿真记录
├── tools/                # 地图保存、仿真和只读诊断工具
└── docs/模拟农田建图测试.md # 阶段 C 仿真/现场建图执行入口
```

成员需要快速查看 SLAM 方案、地图文件、启动命令和 ROS 2 话题/节点清单时，直接看
[`docs/SLAM_MEMBER_HANDOFF.md`](docs/SLAM_MEMBER_HANDOFF.md)。该文档只引用本仓库内
可下载的工程与地图；实时 `ros2 topic list` / `ros2 node list` 请在车端执行文档中的
只读采集脚本。

## 工作流

1. 在本仓库写代码 + 跑离线 `pytest`（无需 ROS）。
2. 上车前由本人在树莓派 colcon build 并实车验证（架空轮、急停就绪、先只读后运动）。
3. 进展同步回主计划 MD 的 §15 更新记录。

车端硬件与定位栈可通过 `deploy/spore-vehicle-stack.service` 作为一个受监督
的 systemd 服务运行。它启动底盘反馈、YDLIDAR、EKF 与 SLAM Toolbox，且不会
启动路线跟踪或自行发布非零 `/cmd_vel`；这样树莓派重启后不会只剩下空容器。

## 状态（2026-09-04）

- `spore_patrol_gnss` 已部署到树莓派 `/home/pi/spore_patrol_ws` 并完成 `enabled=false` 的启动检查；ATGM336H 串口必须在确认设备别名后再显式启用。当前 `/dev/ttyUSB0` 已被 X3 Pro 雷达占用，不能直接把该路径当作并行 GNSS 设备。
- 阶段 C/D 代码已落地；车端 `verify.sh` 通过 91 项路线/安全/GNSS 测试及 YAML 校验。
- canonical 8×6 m 模拟农田已在独立 ROS 域 `42` 实际完成一次无 GUI 建图；9 航点闭环、地图/pose graph 保存、通用栅格和三垄几何验收通过。地图与原始日志已同步至
  `results/sim_farmland_8x6_20260831/`；实机/小花园正式地图和 rosbag 仍待完成。
- 两次同配置低速仿真地图的重复性比较也已通过；垄中心最大偏移 0.050 m（阈值 0.150 m），比较工具为
  `tools/compare_farmland_maps.py`。
- 2026-09-04 已将当前车辆运行所需的底盘、机器人模型、X3 Pro 参数、YDLIDAR ROS 2 驱动、仿真包、仿真地图和成员交接说明同步到本仓库；成员无需再切换到历史雷达/SLAM 分支。
- YDLIDAR-SDK 作为外部构建依赖不提交二进制产物；`tools/setup_ydlidar_dependencies.sh` 固定 SDK/驱动版本并在本地 `.vendor/` 下构建。
- 树莓派已部署并验证 `full_stack.launch.py`：底盘反馈、YDLIDAR、EKF、SLAM Toolbox 由
  `deploy/spore-vehicle-stack.service` 自动恢复；`deploy/spore-rosbridge.service` 提供 9091
  WebSocket 实时桥接。二者均不自动启动路线跟踪或发布非零 `/cmd_vel`。

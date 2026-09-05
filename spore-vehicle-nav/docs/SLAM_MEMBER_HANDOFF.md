# SLAM 成员交接说明

> 适用基线：`spore-vehicle-nav` `main`；本次同步基于 `v0.6.6`（2026-09-01）完成。
> 本文件面向需要直接从本仓库获取 SLAM 工程、地图和运行信息的成员。

## 1. 结论

车辆采用 ROS 2 Humble 下的 `slam_toolbox` 二维激光 SLAM：

```text
YDLIDAR X3 Pro /scan
        ↓
robot_localization EKF
/odom + /imu/data_raw → /odometry/filtered
        ↓
slam_toolbox（异步建图）
        ↓
/map + map→odom
```

当前不是 Cartographer、RTAB-Map 或 Nav2 SLAM。`slam_toolbox` 是系统依赖提供的算法包，
本仓库保存车辆侧的启动和参数工程。

## 2. 仓库内可直接获取的文件

| 内容 | 仓库路径 | 说明 |
|---|---|---|
| SLAM 参数 | [`src/spore_patrol_nav_bringup/config/slam_toolbox.yaml`](../src/spore_patrol_nav_bringup/config/slam_toolbox.yaml) | `/scan`、TF、分辨率、回环、Ceres 参数 |
| EKF 参数 | [`src/spore_patrol_nav_bringup/config/local_ekf.yaml`](../src/spore_patrol_nav_bringup/config/local_ekf.yaml) | `/odom` + `/imu/data_raw` → `/odometry/filtered` |
| EKF+SLAM 启动 | [`src/spore_patrol_nav_bringup/launch/ekf_slam_bringup.launch.py`](../src/spore_patrol_nav_bringup/launch/ekf_slam_bringup.launch.py) | SLAM/EKF，可切换建图和定位 |
| 完整车端启动 | [`src/spore_patrol_nav_bringup/launch/full_stack.launch.py`](../src/spore_patrol_nav_bringup/launch/full_stack.launch.py) | 底盘、雷达、模型、EKF、SLAM |
| 实车地图 YAML | [`results/verify_map_20260901/verify_map.yaml`](../results/verify_map_20260901/verify_map.yaml) | 与同目录 `verify_map.pgm` 配套 |
| 实车地图 PGM | [`results/verify_map_20260901/verify_map.pgm`](../results/verify_map_20260901/verify_map.pgm) | 2026-09-01 临时单垄场地实测 |
| 实车 pose graph | [`results/verify_map_20260901/verify_posegraph.posegraph`](../results/verify_map_20260901/verify_posegraph.posegraph) | SLAM Toolbox 序列化位姿图 |
| 实车数据集 | [`results/verify_map_20260901/verify_posegraph.data`](../results/verify_map_20260901/verify_posegraph.data) | 与 posegraph 配套 |
| 仿真地图全套 | [`results/sim_farmland_8x6_20260831/`](../results/sim_farmland_8x6_20260831/) | 8×6 m 模拟农田，非实车地图 |
| 实时图谱采集脚本 | [`tools/collect_slam_graph.sh`](../tools/collect_slam_graph.sh) | 只读输出 topic/node 清单 |

当前 `maps/` 目录仍只有 `.gitkeep`；实车地图暂存于 `results/verify_map_20260901/`，
它不是学校小花园的正式任务地图。

## 3. 启动方式

在树莓派的 ROS 2 容器内：

```bash
source /opt/ros/humble/setup.bash
source /ws/install/setup.bash

ros2 launch spore_patrol_nav_bringup full_stack.launch.py \
  base_port:=/dev/ttyACM0 \
  lidar_port:=/dev/ydlidar \
  rviz:=false
```

默认 `localization:=false`，即建图模式。若底盘和雷达已经单独启动，可只运行：

```bash
ros2 launch spore_patrol_nav_bringup ekf_slam_bringup.launch.py
```

保存地图：

```bash
ros2 run nav2_map_server map_saver_cli \
  -f /home/pi/spore_patrol_ws/maps/field1

ros2 service call /slam_toolbox/serialize_map \
  slam_toolbox/srv/SerializePoseGraph \
  "{filename: '/home/pi/spore_patrol_ws/maps/field1'}"
```

定位模式加载的是序列化 pose graph，文件名不带扩展名：

```bash
ros2 launch spore_patrol_nav_bringup ekf_slam_bringup.launch.py \
  localization:=true \
  map_file_name:=/home/pi/spore_patrol_ws/maps/field1
```

## 4. 话题和节点

### SLAM Toolbox 自身发布

| 话题 | 类型 | 用途 |
|---|---|---|
| `/map` | `nav_msgs/msg/OccupancyGrid` | 占据栅格地图 |
| `/map_metadata` | `nav_msgs/msg/MapMetaData` | 地图元数据 |
| `/pose` | `geometry_msgs/msg/PoseWithCovarianceStamped` | SLAM 位姿 |
| `/slam_toolbox/graph_visualization` | `visualization_msgs/msg/MarkerArray` | 位姿图可视化 |
| `/slam_toolbox/scan_visualization` | `sensor_msgs/msg/LaserScan` | 配准扫描可视化 |
| `/slam_toolbox/update` | `visualization_msgs/msg/InteractiveMarkerUpdate` | 交互更新 |
| `/tf` | `tf2_msgs/msg/TFMessage` | `map→odom` |

### 完整硬件栈还会发布

`/odom`、`/imu/data_raw`、`/battery_state`、`/diagnostics`、`/scan`、`/point_cloud`、
`/odometry/filtered`、`/tf` 和 `/tf_static`。

完整栈（`rviz:=false`、未启动路线跟踪）的稳定节点名：

```text
/ekf_local_filter_node
/robot_state_publisher
/slam_toolbox
/spore_patrol_base_driver
/ydlidar_ros2_driver_node
```

启用 RViz 会增加 `/rviz2`；部分 ROS 版本还会显示
`transform_listener_impl_*` 辅助节点。

注意：`ros2 topic list` 展示的是 DDS 图谱中的全部话题，因此可能包含只有订阅者的
`/cmd_vel`、`/set_pose`、`/joint_states` 和 `/slam_toolbox/feedback`，它们不等于当前
一定有发布者。`full_stack.launch.py` 不启动路线跟踪，也不发布非零 `/cmd_vel`。

## 5. 实时清单采集

实时 topic/node 列表不能随代码仓库静态固定，必须在车端当前 ROS 域内执行：

```bash
sudo docker exec humble bash -lc \
  '/ws/tools/collect_slam_graph.sh'
```

脚本只执行 `ros2 topic list` 和 `ros2 node list`，不会发送运动指令。车端 ROS 域应为
`ROS_DOMAIN_ID=77`。当前开发机没有运行车辆节点时，得到的只会是系统默认的
`/parameter_events`、`/rosout`，不能当作车端快照。

本次开发机只读快照（`ROS_DOMAIN_ID=77`、`ROS_LOCALHOST_ONLY=1`）为：

```text
ros2 topic list:
/parameter_events
/rosout

ros2 node list:
(empty)
```

## 6. 工程边界

本次同步已把当前运行所需的 `spore_patrol_base_driver`、`spore_patrol_bringup`、
`spore_patrol_description`、`spore_patrol_lidar`、`spore_patrol_sim` 和
`ydlidar_ros2_driver` 源码放入本仓库 `src/`，成员可直接从本仓库组装工作区。系统级
依赖仍需在目标机器安装：`slam_toolbox`、`robot_localization`、`nav2_map_server`、
`gazebo_ros` 及 ROS 2 Humble 基础包；依赖名称也写入各包的 `package.xml`。

当前统一车端入口是 `spore_patrol_nav_bringup`。旧的独立
`spore_patrol_localization/mapping_localization.launch.py`（含 IMU 零偏校准）不作为
本仓库当前入口，避免同时启动两套 EKF/SLAM 和重复发布 TF。

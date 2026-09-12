# 小车 IMU 调用与使用指南

## 1. 当前实现结论

项目已经编写 IMU 调用程序。当前方案不是树莓派直接通过 I²C/SPI 读取 IMU，而是：

```text
ICM20948 → STM32 底盘反馈帧 → ROS2 底盘驱动 → /imu/data_raw
                                           ↓
                              零偏校准 → /imu/data_calibrated
                                           ↓
                                  robot_localization EKF
```

底盘驱动从 STM32 串口读取 IMU 原始加速度和陀螺仪数据，转换为 ROS2 标准
`sensor_msgs/msg/Imu` 消息。

## 2. 主要话题

| 话题 | 类型 | 用途 |
|---|---|---|
| `/imu/data_raw` | `sensor_msgs/msg/Imu` | STM32 反馈的原始 IMU 数据，已完成单位转换 |
| `/imu/data_calibrated` | `sensor_msgs/msg/Imu` | 启动静止校准后的 IMU 数据，供 EKF 使用 |
| `/odometry/filtered` | `nav_msgs/msg/Odometry` | 轮速与 IMU 融合后的局部里程计 |

当前 EKF 只融合 IMU 的 `angular_velocity.z`（Z 轴角速度）。加速度、X/Y 轴角速度
和姿态四元数虽然会发布，但暂未参与融合；代码明确将姿态四元数标记为不可用。

## 3. 启动方法

在已经完成 ROS2 工作空间编译并加载环境后，启动底盘、IMU 校准和 EKF：

```bash
ros2 launch spore_patrol_localization hardware_localization.launch.py \
  port:=/dev/ttyACM0 lidar:=false rviz:=false
```

启动后必须让小车保持静止约 10 秒。校准默认要求至少采集 100 个样本，检测到运动
会自动重新开始校准。

## 4. 检查是否正常工作

```bash
# 检查原始 IMU 是否有数据
ros2 topic echo /imu/data_raw --once
ros2 topic hz /imu/data_raw

# 校准完成后检查校准数据和融合结果
ros2 topic echo /imu/data_calibrated --once
ros2 topic echo /odometry/filtered --once

# 查看 IMU 校准状态
ros2 topic echo /diagnostics
```

需要重新校准时执行：

```bash
ros2 service call /imu_bias_calibrator/recalibrate std_srvs/srv/Trigger "{}"
```

## 5. 常见问题

- `/imu/data_raw` 没有数据：检查 STM32 是否正在发送包含 IMU 字段的状态帧、串口设备是否为 `/dev/ttyACM0`，以及波特率是否为 `115200`。
- `/imu/data_calibrated` 没有数据：确认小车静止等待校准完成；运动、时间回退或角速度超过阈值都会使校准重新开始。
- EKF 没有正确融合：确认使用的是 `/imu/data_calibrated`，并检查 `/odometry/filtered` 是否持续发布。

## 6. 代码位置

- 底盘 IMU 发布：`src/spore_patrol_base_driver/spore_patrol_base_driver/base_driver_node.py`
- 串口协议及单位转换：`src/spore_patrol_base_driver/spore_patrol_base_driver/protocol.py`
- 串口和 IMU 参数：`src/spore_patrol_base_driver/config/base_driver.yaml`
- 零偏校准：`src/spore_patrol_localization/scripts/imu_bias_calibrator.py`
- EKF 参数：`src/spore_patrol_localization/config/local_ekf.yaml`

> 注意：`spore-vehicle-nav` 版本直接将 `/imu/data_raw` 接入 EKF，没有启用上述软件零偏校准；进行开发和测试时请先确认使用的工程目录。

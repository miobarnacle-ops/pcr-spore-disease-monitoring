# 车辆导航公开交接说明

这是可公开发送的车辆导航交接版本，不包含实际网络、账号或设备凭据。需要实机联调的成员应向项目负责人单独获取私密运行参数。

## 硬件

- 底盘：WHEELTEC R550 PLUS，C50C/STM32 控制板；
- 激光雷达：YDLIDAR X3 Pro；
- 主控：Raspberry Pi 5，8 GB；
- GNSS：ATGM336H，当前为普通单点 GNSS 适配，不能直接宣称 RTK Float/Fix 或小于 0.5 m 精度；
- 必须准备物理急停、稳定供电、串口线和安全测试场地。

## 软件拓扑

```text
底盘 -> /odom /imu/data_raw /battery_state
雷达 -> /scan
GNSS -> /fix /gps/status
              |
              v
robot_localization EKF -> /odometry/filtered
              |
              v
SLAM Toolbox -> map -> odom
              |
              v
route_tracker -> /cmd_vel + /mission/status
              |
              v
rosbridge -> Web 控制台
```

## 离线检查

```bash
cd spore-vehicle-nav
./verify.sh
```

实机检查顺序：获取私密主机参数 → 进入 Docker Humble → 确认串口映射 → 只读检查 → 架空低速 → 分级路线和采样联动。failsafe 未达到目标阈值前，不得把它当作唯一安全措施。

## 私密参数

以下信息不在公开仓库中：热点 SSID/密码、树莓派地址和登录凭据、ROS Domain ID、rosbridge 实际 URL、DDS 对端配置、udev/设备权限细节和本机 sudo 凭据。请向项目负责人单独索取，并使用个人账号与独立密钥。


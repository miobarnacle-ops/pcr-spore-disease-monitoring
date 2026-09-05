# `spore_patrol_gnss`

ATGM336H 的 ROS 2 Humble NMEA 适配包。协议解析、WGS84→本地 ENU 数学和 ROS 串口 I/O 分层，前两层可在没有设备和 ROS 运行时的环境中测试。

## 当前硬件边界

本包按当前成员反馈适配：`/dev/ttyUSB0`、9600 baud、NMEA-0183、GGA/GLL/VTG。ATGM336H 当前按普通单点 GNSS 处理，状态输出为 `single`；不宣称 RTK Float/Fix，不支持 RTCM 差分，也不发布 `<0.5 m` 精度结论。

## 安全默认值

```bash
ros2 launch spore_patrol_gnss gnss.launch.py
```

默认 `enabled:=false`，不会打开串口。明确确认设备和现场条件后才可：

```bash
ros2 launch spore_patrol_gnss gnss.launch.py enabled:=true port:=/dev/ttyUSB0 baud_rate:=9600
```

本包不订阅或发布 `/cmd_vel`，不会驱动车辆。`single_fix_std_m` 只是保守的可配置协方差估计，必须在真实精度测试后再决定是否用于融合；不能把它当作测量结果。

## 输出

| 话题 | 类型 | 含义 |
|---|---|---|
| `/fix` | `sensor_msgs/NavSatFix` | 经纬度/海拔；普通有效定位为 `STATUS_FIX`，语义质量在 `/gps/status` 中为 `single` |
| `/gps/status` | `std_msgs/String` JSON | quality、卫星数、HDOP、ENU 是否启用、解析错误计数 |
| `/gps/velocity` | `geometry_msgs/Vector3Stamped` | `vector.x` 速度 m/s，`vector.y` 航向角 deg，`vector.z` 速度 km/h |
| `/gps/speed_mps` | `std_msgs/Float32` | VTG 速度 m/s |
| `/gps/course_deg` | `std_msgs/Float32` | VTG 真航向角 deg |
| `/gps/raw_nmea` | `std_msgs/String` | 原始逐行 NMEA（不得包含账号/密码） |
| `/gps/diagnostics` | `diagnostic_msgs/DiagnosticArray` | 串口、数据新鲜度和解析健康 |
| `/gps/enu` | `geometry_msgs/PointStamped` | 启用并配置测量原点后的本地 ENU 米制坐标 |

## 离线验证

```bash
cd src/spore_patrol_gnss
python3 -m pytest tests/ -q
```

fixture 是协议形状和数学回归输入；它不等同于原始现场测量记录。获得真实 NMEA 日志后，应另行保存原始证据并对静态/运动误差与独立真值进行统计。

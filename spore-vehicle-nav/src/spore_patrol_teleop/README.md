# spore_patrol_teleop

简洁的 ROS 2 终端键盘遥控控制台。它只发布标准
`geometry_msgs/msg/Twist` 到 `/cmd_vel`，由已有的
`spore_patrol_base_driver` 负责串口和 STM32 通信。

## 启动

在电脑或树莓派上，确保该终端与车端处于同一个 ROS 2 网络域：

```bash
source /opt/ros/humble/setup.bash
source /ws/install/setup.bash
ros2 run spore_patrol_teleop keyboard_teleop
```

也可以通过 launch 调整初始速度：

```bash
ros2 launch spore_patrol_teleop keyboard_teleop.launch.py \
  linear_speed_mps:=0.05 \
  angular_speed_radps:=0.15
```

## 按键

```text
W       前进
S       后退
A       原地左转
D       原地右转
空格/X  停车
+/-     调整速度
Q       退出
```

控制台不设置确认弹窗。终端持续收到运动按键时才发布非零速度；按键输入停止
超过 0.25 秒后自动发布零速度，退出时也会发送短暂的零速度序列。

首轮实车使用时不要同时运行 `route_tracker`、另一个 teleop 节点或其他会发布
`/cmd_vel` 的程序。物理急停仍必须在操作者手边；软件停车不是物理急停。

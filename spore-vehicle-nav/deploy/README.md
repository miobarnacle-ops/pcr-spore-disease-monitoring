# 树莓派服务部署

本目录的服务只负责恢复传感器、定位和 WebSocket 数据链路，不会自动启动
路线跟踪，也不会自行发布非零 `/cmd_vel`。

- `spore-vehicle-stack.service`：底盘反馈、YDLIDAR、EKF、SLAM Toolbox。
- `spore-rosbridge.service`：9091 端口的 rosbridge WebSocket 网关。

服务运行在树莓派宿主机上，通过 `humble` Docker 容器执行 ROS 2 Humble。
雷达设备在容器内固定映射为 `/dev/ttyUSB0`，同时建立 `/dev/ydlidar` 别名。

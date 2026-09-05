# Spore Patrol Nav Bringup (Stage C)

Bring-up package for the **EKF + SLAM Toolbox** mapping/localization stack of
the spore patrol vehicle (WHEELTEC R550 PLUS / Raspberry Pi 5, ROS 2 Humble).
This package is **config + launch only**; it contains no algorithm code.

It starts:

- `robot_localization` EKF (`ekf_local_filter_node`) — fuses the base driver
  wheel odometry (`/odom`: forward + zero lateral velocity) with the ICM20948
  (C50C) yaw rate (`/imu/data_raw`), publishes `/odometry/filtered` and owns
  the `odom -> base_footprint` transform.
- SLAM Toolbox (`slam_toolbox`) — owns the `map -> odom` transform. Async
  mapping mode by default, or localization mode against a saved pose graph.

For a single supervised hardware start (including the base driver and
YDLIDAR), use `full_stack.launch.py`. It is safe to run while the vehicle is
stationary and does not start route tracking or publish non-zero `/cmd_vel`:

```bash
ros2 launch spore_patrol_nav_bringup full_stack.launch.py \
    base_port:=/dev/ttyACM0 lidar_port:=/dev/ydlidar rviz:=false
```

## TF chain

```
map -> odom -> base_footprint -> base_link -> laser_link
```

Exactly one publisher per transform:

| transform                              | publisher                          |
|----------------------------------------|------------------------------------|
| `map -> odom`                          | SLAM Toolbox                       |
| `odom -> base_footprint`               | EKF (`robot_localization`)         |
| `base_footprint -> base_link -> laser_link` | base driver / robot_state_publisher |

## Prerequisites (must already be running)

The base driver and lidar are started by the main hardware bringup and are
assumed running by default:

- `/odom` (`nav_msgs/Odometry`) — base driver.
- `/imu/data_raw` (`sensor_msgs/Imu`) — base driver (ICM20948 on C50C).
- `/scan` (`sensor_msgs/LaserScan`) — YDLIDAR driver, frame `laser_link`.
- `base_footprint -> base_link -> laser_link` TF — `robot_state_publisher`.

You can start the base driver and lidar from this launch instead with
`start_base_driver:=true` and `start_lidar:=true`.

## Build

```bash
cd ~/spore_patrol_ws
colcon build --packages-select spore_patrol_nav_bringup
source install/setup.bash
```

## Mapping (Stage C)

```bash
ros2 launch spore_patrol_nav_bringup ekf_slam_bringup.launch.py
```

With the base driver + lidar brought up in one command:

```bash
ros2 launch spore_patrol_nav_bringup ekf_slam_bringup.launch.py \
    start_base_driver:=true start_lidar:=true
```

Keep the chassis stationary at startup (the raw yaw rate is fused without a
software bias calibrator). Drive slowly (wheels lifted, e-stop ready) while the
map fills in.

## Saving the map

While the mapping bringup is still running, open a second terminal and run:

```bash
# Occupancy grid (pgm + yaml)
ros2 run nav2_map_server map_saver_cli -f ~/spore_patrol_ws/maps/field1

# Pose graph (required for localization mode)
ros2 service call /slam_toolbox/serialize_map \
    slam_toolbox/srv/SerializePoseGraph \
    "{filename: \"/home/pi/spore_patrol_ws/maps/field1\"}"
```

## Localization

```bash
ros2 launch spore_patrol_nav_bringup ekf_slam_bringup.launch.py \
    localization:=true \
    map_file_name:=/home/pi/spore_patrol_ws/maps/field1
```

`map_file_name` is the serialized pose graph path with the extension omitted.
The initial pose defaults to the map origin; set `map_start_pose` in
`config/slam_toolbox.yaml` if a different start pose is needed.

## Checks

```bash
ros2 topic hz /odom
ros2 topic hz /imu/data_raw
ros2 topic hz /odometry/filtered
ros2 topic hz /scan
ros2 run tf2_ros tf2_echo odom base_footprint
ros2 run tf2_ros tf2_echo map odom
```

## Launch arguments

| argument              | default            | description                                            |
|-----------------------|--------------------|--------------------------------------------------------|
| `use_sim_time`        | `false`            | use `/clock` instead of the host clock                 |
| `ekf_params_file`     | `config/local_ekf.yaml` | EKF parameter file                                 |
| `slam_params_file`    | `config/slam_toolbox.yaml` | SLAM Toolbox parameter file                     |
| `localization`        | `false`            | localization mode instead of mapping                   |
| `map_file_name`       | `""`               | pose graph to load (required when `localization:=true`)|
| `publish_tf`          | `true`             | EKF publishes `odom -> base_footprint`                 |
| `start_base_driver`   | `false`            | also start the base driver                             |
| `base_port`           | `/dev/ttyACM0`     | base driver serial device                              |
| `start_lidar`         | `false`            | also start the YDLIDAR driver                          |
| `lidar_port`          | `/dev/ydlidar`     | lidar serial device                                    |
| `save_map`            | `false`            | one-shot map dump (prefer the CLI, see above)          |
| `map_save_path`       | `~/spore_patrol_maps/map` | output path for `save_map`                      |

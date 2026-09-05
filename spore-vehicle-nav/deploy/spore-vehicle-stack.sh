#!/usr/bin/env bash
set -euo pipefail

# Host-side supervisor for the stationary-capable ROS 2 stack. The container
# is deliberately kept separate from the host ROS installation; this script
# only starts sensor/localization bring-up and never starts route tracking.
container_name="humble"

stop_stack() {
  /usr/bin/docker exec "${container_name}" bash -lc '
    set +e
    # docker exec is not the parent of the ROS children in the container, so
    # explicitly terminate the complete full-stack launch tree on stop.
    for pattern in \
      "[/]opt/ros/humble/bin/ros2 launch spore_patrol_nav_bringup full_stack.launch.py" \
      "[/]ws/install/spore_patrol_base_driver/lib/spore_patrol_base_driver/base_driver_node" \
      "[/]ws/install/ydlidar_ros2_driver/lib/ydlidar_ros2_driver/ydlidar_ros2_driver_node" \
      "[/]opt/ros/humble/lib/robot_localization/ekf_node" \
      "[/]opt/ros/humble/lib/slam_toolbox/async_slam_toolbox_node" \
      "[/]opt/ros/humble/lib/robot_state_publisher/robot_state_publisher"; do
      pgrep -f "${pattern}" | while read -r pid; do kill -TERM "${pid}" 2>/dev/null || true; done
    done
    sleep 3
    for pattern in \
      "[/]ws/install/spore_patrol_base_driver/lib/spore_patrol_base_driver/base_driver_node" \
      "[/]ws/install/ydlidar_ros2_driver/lib/ydlidar_ros2_driver/ydlidar_ros2_driver_node" \
      "[/]opt/ros/humble/lib/robot_localization/ekf_node" \
      "[/]opt/ros/humble/lib/slam_toolbox/async_slam_toolbox_node" \
      "[/]opt/ros/humble/lib/robot_state_publisher/robot_state_publisher"; do
      pgrep -f "${pattern}" | while read -r pid; do kill -KILL "${pid}" 2>/dev/null || true; done
    done
  ' || true
}

if [[ "${1:-}" == "stop" ]]; then
  stop_stack
  exit 0
fi

for _ in $(seq 1 30); do
  running="$(/usr/bin/docker inspect --format '{{.State.Running}}' "${container_name}" 2>/dev/null || true)"
  if [[ "${running}" == "true" ]]; then
    break
  fi
  /usr/bin/docker start "${container_name}" >/dev/null 2>&1 || true
  sleep 2
done

running="$(/usr/bin/docker inspect --format '{{.State.Running}}' "${container_name}" 2>/dev/null || true)"
if [[ "${running}" != "true" ]]; then
  echo "Docker container ${container_name} is not running." >&2
  exit 1
fi

exec /usr/bin/docker exec "${container_name}" bash -lc '
  # ROS setup scripts reference optional variables while they are sourced;
  # enable nounset only after the environment has been initialized.
  set -eo pipefail
  # The host udev alias is not automatically visible inside this container.
  ln -sfn /dev/ttyUSB0 /dev/ydlidar
  source /opt/ros/humble/setup.bash
  source /ws/install/setup.bash
  source /ws/tools/ydlidar_env.sh
  set -u
  exec ros2 launch spore_patrol_nav_bringup full_stack.launch.py \
    base_port:=/dev/ttyACM0 \
    lidar_port:=/dev/ttyUSB0 \
    rviz:=false \
    localization:=false
'

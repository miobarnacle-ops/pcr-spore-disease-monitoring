#!/usr/bin/env bash

# Read-only ROS 2 graph snapshot. This script never publishes motion commands.
source /opt/ros/humble/setup.bash

script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
workspace_root="$(CDPATH= cd -- "${script_directory}/.." && pwd)"
for setup_file in \
  "${workspace_root}/install/setup.bash" \
  /ws/install/setup.bash \
  /home/pi/spore_patrol_ws/install/setup.bash; do
  if [ -f "$setup_file" ]; then
    # shellcheck disable=SC1090
    source "$setup_file"
    break
  fi
done

set -u
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-77}"

echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "=== ros2 topic list ==="
timeout 15s ros2 topic list | sort
echo "=== ros2 node list ==="
timeout 15s ros2 node list | sort

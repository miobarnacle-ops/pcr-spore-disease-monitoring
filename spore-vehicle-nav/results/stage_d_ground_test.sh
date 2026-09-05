#!/usr/bin/env bash
# Stage D ground test: 1m straight line at 0.12 m/s, sampling stop at end.
set -u
CE="sudo docker exec humble bash -lc"

echo "=== pose BEFORE ==="
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 4 ros2 run tf2_ros tf2_echo odom base_footprint 2>&1 | grep -A2 Translation | head -3"

echo "=== subscribe /mission/status (30s) ==="
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 30 ros2 topic echo /mission/status --field data > /tmp/ground_status.log 2>&1" &
sleep 2

echo "=== start route_tracker (25s lifetime) ==="
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 25 ros2 run spore_patrol_route_validation route_tracker --ros-args -p route_file:=/ws/routes/sample_route.json -p start_pose_x:=1.617 -p start_pose_y:=-2.626 -p start_pose_yaw:=-2.66 > /tmp/ground_tracker.log 2>&1" &
sleep 12

echo "=== /cmd_vel sample during drive ==="
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 3 ros2 topic echo /cmd_vel --once 2>&1 | grep -A4 linear | head -6"

echo "=== pose at 12s ==="
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 4 ros2 run tf2_ros tf2_echo odom base_footprint 2>&1 | grep -A2 Translation | head -3"

sleep 8

echo "=== pose FINAL ==="
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 4 ros2 run tf2_ros tf2_echo odom base_footprint 2>&1 | grep -A2 Translation | head -3"

echo "=== mission status captured ==="
$CE "cat /tmp/ground_status.log 2>/dev/null | grep -v WARNING | head -30"

echo "=== tracker log ==="
$CE "cat /tmp/ground_tracker.log 2>/dev/null | head -10"

echo "=== done ==="
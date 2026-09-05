#!/usr/bin/env bash
# Stage D smoke test: run route_tracker (wheels lifted) against the live stack.
# Runs on the Pi HOST; invokes docker exec for ROS commands.
set -u
ROUTE_FILE="/ws/routes/sample_route.json"
START_X="1.121"; START_Y="-0.002"; START_YAW="-0.939"

echo "=== [1] preflight: current cmd_vel topic info ==="
sudo docker exec humble bash -lc "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 4 ros2 topic info /cmd_vel 2>&1 | head -6"

echo
echo "=== [2] subscribe /mission/status (background, catches first transition) ==="
sudo docker exec -d humble bash -lc "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 20 ros2 topic echo /mission/status > /tmp/status.log 2>&1"
sleep 2

echo "=== [3] start route_tracker (detached, 22s lifetime, 0.12 m/s cap) ==="
sudo docker exec -d humble bash -lc "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 22 ros2 run spore_patrol_route_validation route_tracker --ros-args -p route_file:=${ROUTE_FILE} -p start_pose_x:=${START_X} -p start_pose_y:=${START_Y} -p start_pose_yaw:=${START_YAW} > /tmp/tracker.log 2>&1"
sleep 5

echo "=== [4] /cmd_vel sample (should be non-zero linear.x) ==="
sudo docker exec humble bash -lc "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 3 ros2 topic echo /cmd_vel --once 2>&1 | grep -E 'linear|angular' | head -6"

echo "=== [5] /cmd_vel publish rate (need >= 5 Hz for watchdog) ==="
sudo docker exec humble bash -lc "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 5 ros2 topic hz /cmd_vel --window 20 2>&1 | tail -2"

echo "=== [6] /mission/status captured so far ==="
sudo docker exec humble bash -lc "cat /tmp/status.log 2>/dev/null | head -12"
sleep 8

echo "=== [7] final /mission/status tail ==="
sudo docker exec humble bash -lc "cat /tmp/status.log 2>/dev/null | tail -8"

echo "=== [8] tracker node log ==="
sudo docker exec humble bash -lc "cat /tmp/tracker.log 2>/dev/null | head -20"

echo
echo "=== done ==="

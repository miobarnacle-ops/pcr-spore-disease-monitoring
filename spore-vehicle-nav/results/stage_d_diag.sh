#!/usr/bin/env bash
# Diagnostic: is /mission/status actually published while route_tracker runs?
set -u
CE="sudo docker exec humble bash -lc"

echo "--- start tracker (detached 12s) ---"
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 12 ros2 run spore_patrol_route_validation route_tracker --ros-args -p route_file:=/ws/routes/sample_route.json -p start_pose_x:=1.121 -p start_pose_y:=-0.002 -p start_pose_yaw:=-0.939 > /tmp/t3.log 2>&1" &
sleep 4

echo "--- topic list (mission/cmd_vel) ---"
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 3 ros2 topic list 2>/dev/null | grep -E 'mission|cmd_vel'"

echo "--- topic info /mission/status ---"
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 3 ros2 topic info /mission/status 2>&1 | head -5"

echo "--- echo /mission/status (data field) 3s ---"
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 3 ros2 topic echo /mission/status --field data 2>&1 | head -6"

echo "--- node log ---"
$CE "cat /tmp/t3.log 2>/dev/null | head -8"
echo "--- done ---"
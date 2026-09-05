#!/usr/bin/env bash
# Read-only SLAM status report. No motion commands are sent.
set -u
CE="sudo docker exec humble bash -lc"

echo "=== [1] Pi 主机已保存的地图文件 ==="
ls -la ~/spore_patrol_ws/maps/ 2>/dev/null || echo "(无 maps 目录)"
find ~/spore_patrol_ws/maps -type f \( -name "*.pgm" -o -name "*.yaml" -o -name "*.posegraph" -o -name "*.data" -o -name "*.serialized" \) -exec ls -la {} \; 2>/dev/null

echo
echo "=== [2] 容器内 /ws/maps ==="
$CE "ls -la /ws/maps 2>/dev/null"

echo
echo "=== [3] slam_toolbox 节点与模式 ==="
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && ros2 node list 2>/dev/null | grep -i slam; timeout 4 ros2 param get /slam_toolbox mode 2>&1"

echo
echo "=== [4] /map 发布频率 ==="
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 5 ros2 topic hz /map --window 5 2>&1 | tail -2"

echo
echo "=== [5] /map 元信息 ==="
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 6 ros2 topic echo /map --once --field info 2>&1 | grep -E 'resolution|width|height|frame_id|^  x:|^  y:' | head -8"

echo
echo "=== [6] 栅格质量统计 ==="
$CE "source /opt/ros/humble/setup.bash && source /ws/install/setup.bash && timeout 15 python3 /ws/tools/map_check.py 2>&1 | tail -8"

echo
echo "=== [7] posegraph/序列化文件搜索（全工作区） ==="
find ~/spore_patrol_ws -maxdepth 4 \( -name "*.posegraph" -o -name "*.data" -o -name "*.serialized" \) -exec ls -la {} \; 2>/dev/null || true
echo "--- done ---"
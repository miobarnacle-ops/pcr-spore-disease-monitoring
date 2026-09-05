#!/usr/bin/env bash
set -euo pipefail

# Headless Stage C simulation smoke test. This script only publishes Twist
# messages to the Gazebo robot started by this script; it never opens a real
# serial device and never touches the physical vehicle.

script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
workspace_root="$(CDPATH= cd -- "${script_directory}/.." && pwd)"
# Keep the simulation isolated from the vehicle's ROS domain and force ROS
# helper scripts to use Ubuntu's Python 3.10, matching the Humble install.
export PATH="/opt/ros/humble/bin:/usr/bin:/bin:${PATH}"
export ROS_DOMAIN_ID="${SIM_ROS_DOMAIN_ID:-42}"
export ROS_LOCALHOST_ONLY="${SIM_ROS_LOCALHOST_ONLY:-1}"
world_file="${workspace_root}/src/spore_patrol_sim/worlds/farmland_8x6.world"
layout_file="${workspace_root}/src/spore_patrol_sim/config/farmland_layout.json"
default_slam_params_file="${workspace_root}/src/spore_patrol_sim/config/sim_mapping.yaml"
slam_params_file="${SIM_SLAM_PARAMS_FILE:-${default_slam_params_file}}"
map_validator="${workspace_root}/tools/validate_saved_map.py"
farmland_map_validator="${workspace_root}/tools/validate_farmland_map.py"
mapping_driver="${workspace_root}/tools/sim_mapping_driver.py"
timestamp="$(date +%Y%m%d_%H%M%S)"
result_directory="${workspace_root}/tests/results/${timestamp}_sim_farmland_8x6"
map_base="${result_directory}/sim_farmland_8x6"
launch_pid=""

usage() {
  cat <<'EOF'
Usage: tools/sim_mapping_smoke.sh [--no-drive]

Starts the canonical 8 m x 6 m Gazebo field headlessly with SLAM Toolbox.
By default it drives a deterministic low-speed two-corridor loop, saves the
occupancy map and serialized pose graph, then runs the offline map checker.
--no-drive only checks that Gazebo, /scan, /odom and /map start; it does not
produce a meaningful map. Set SIM_SLAM_PARAMS_FILE to run a diagnostic SLAM
profile without changing the canonical installed configuration.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
no_drive=false
if [[ "${1:-}" == "--no-drive" ]]; then
  no_drive=true
elif [[ $# -gt 0 ]]; then
  usage >&2
  exit 2
fi

for command_name in ros2 python3; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${command_name} was not found; source ROS 2 Humble and the workspace first." >&2
    exit 2
  fi
done
if [[ ! -f "${world_file}" || ! -f "${layout_file}" || ! -f "${slam_params_file}" || ! -f "${map_validator}" || ! -f "${farmland_map_validator}" || ! -f "${mapping_driver}" ]]; then
  echo "simulation source or validation tool is missing" >&2
  exit 2
fi

python3 "${workspace_root}/tools/validate_farmland_layout.py"
mkdir -p "${result_directory}"
{
  date --iso-8601=seconds
  printf 'world=%s\n' "${world_file}"
  printf 'layout=%s\n' "${layout_file}"
  printf 'slam_params=%s\n' "${slam_params_file}"
  printf 'mode=headless_gazebo_slam\n'
  printf 'drive=%s\n' "$([[ "${no_drive}" == true ]] && echo false || echo true)"
} > "${result_directory}/metadata.txt"

cleanup() {
  if [[ -n "${launch_pid}" ]]; then
    # setsid below makes launch_pid the process-group leader. Signal the full
    # group so Gazebo and ROS children cannot survive an early test failure.
    kill -INT -- "-${launch_pid}" 2>/dev/null || true
    for _ in $(seq 1 20); do
      if ! kill -0 "${launch_pid}" 2>/dev/null; then
        break
      fi
      sleep 0.1
    done
    kill -TERM -- "-${launch_pid}" 2>/dev/null || true
    sleep 0.2
    kill -KILL -- "-${launch_pid}" 2>/dev/null || true
    wait "${launch_pid}" 2>/dev/null || true
  fi

  # gazebo_ros launches gzserver through a separate shell/session.  It may
  # therefore outlive the ros2 launch process group even after a clean exit.
  # Match only this canonical world so an unrelated Gazebo instance is never
  # touched, then terminate its process group before returning to the shell.
  local gazebo_pid gazebo_pgid
  while read -r gazebo_pid; do
    [[ "${gazebo_pid}" =~ ^[0-9]+$ ]] || continue
    gazebo_pgid="$(ps -o pgid= -p "${gazebo_pid}" | tr -d ' ')"
    if [[ "${gazebo_pgid}" =~ ^[0-9]+$ && "${gazebo_pgid}" != "0" ]]; then
      kill -INT -- "-${gazebo_pgid}" 2>/dev/null || true
      sleep 0.2
      kill -TERM -- "-${gazebo_pgid}" 2>/dev/null || true
      sleep 0.2
      kill -KILL -- "-${gazebo_pgid}" 2>/dev/null || true
    fi
  done < <(pgrep -f "gzserver .*${world_file}" || true)
}
trap cleanup EXIT

# Use an isolated process group; cleanup must also work when the map checker or
# map saver exits early.
setsid ros2 launch spore_patrol_sim sim.launch.py \
  world:="${world_file}" \
  slam_params_file:="${slam_params_file}" \
  gui:=false \
  rviz:=false \
  slam:=true \
  use_sim_time:=true \
  > "${result_directory}/simulation.log" 2>&1 &
launch_pid=$!

wait_for_topic() {
  local topic="$1"
  local attempts=0
  while (( attempts < 60 )); do
    if ! kill -0 "${launch_pid}" 2>/dev/null; then
      echo "Simulation launch exited before ${topic} became available; see ${result_directory}/simulation.log" >&2
      return 1
    fi
    if timeout 2s ros2 topic echo "${topic}" --once >/dev/null 2>&1; then
      return 0
    fi
    attempts=$((attempts + 1))
  done
  echo "Timed out waiting for ${topic}; see ${result_directory}/simulation.log" >&2
  return 1
}

wait_for_topic /scan
wait_for_topic /odom
wait_for_topic /map

if [[ "${no_drive}" == true ]]; then
  echo "PASS simulation startup only (no map saved)"
  exit 0
fi

# Start in the lower corridor, use the two headlands to visit both corridors
# and both field ends, then return to the start position. The driver closes
# each segment against /odom, so collision or a stalled model is reported as
# a failed mapping run instead of silently saving an under-covered map.
python3 "${mapping_driver}" \
  --speed "${SIM_MAPPING_SPEED:-0.20}" \
  --segment-timeout "${SIM_MAPPING_SEGMENT_TIMEOUT:-45}" \
  --log "${result_directory}/trajectory.log"

ros2 run nav2_map_server map_saver_cli \
  -f "${map_base}" \
  --ros-args -p save_map_timeout:=60.0 \
  > "${result_directory}/map_saver.log" 2>&1

ros2 service call \
  /slam_toolbox/serialize_map \
  slam_toolbox/srv/SerializePoseGraph \
  "{filename: \"${map_base}\"}" \
  > "${result_directory}/posegraph_saver.log" 2>&1

python3 "${map_validator}" "${map_base}.yaml" \
  > "${result_directory}/map_validation.log"
python3 "${farmland_map_validator}" "${map_base}.yaml" \
  --layout "${layout_file}" \
  > "${result_directory}/farmland_map_validation.log"
cp "${layout_file}" "${result_directory}/farmland_layout.json"
echo "PASS simulated farmland mapping smoke test"
echo "- results=${result_directory}"

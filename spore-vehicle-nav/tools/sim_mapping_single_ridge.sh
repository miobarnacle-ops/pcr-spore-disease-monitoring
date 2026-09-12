#!/usr/bin/env bash
set -euo pipefail

# Headless single-ridge Gazebo + SLAM run.  This script is simulation-only:
# it publishes /cmd_vel to the Gazebo model and never opens a serial device.

script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
workspace_root="$(CDPATH= cd -- "${script_directory}/.." && pwd)"
export PATH="/opt/ros/humble/bin:/usr/bin:/bin:${PATH}"
export ROS_DOMAIN_ID="${SIM_ROS_DOMAIN_ID:-43}"
export ROS_LOCALHOST_ONLY="${SIM_ROS_LOCALHOST_ONLY:-1}"

world_file="${workspace_root}/src/spore_patrol_sim/worlds/single_ridge_8m.world"
layout_file="${workspace_root}/src/spore_patrol_sim/config/single_ridge_layout.json"
default_slam_params_file="${workspace_root}/src/spore_patrol_sim/config/single_ridge_mapping.yaml"
slam_params_file="${SIM_SLAM_PARAMS_FILE:-${default_slam_params_file}}"
layout_validator="${workspace_root}/tools/validate_single_ridge_layout.py"
map_validator="${workspace_root}/tools/validate_saved_map.py"
farmland_map_validator="${workspace_root}/tools/validate_farmland_map.py"
mapping_driver="${workspace_root}/tools/single_ridge_mapping_driver.py"
timestamp="$(date +%Y%m%d_%H%M%S)"
result_directory="${workspace_root}/results/${timestamp}_sim_single_ridge_8m"
map_base="${result_directory}/sim_single_ridge_8m"
launch_pid=""

usage() {
  cat <<'EOF'
Usage: tools/sim_mapping_single_ridge.sh [--no-drive]

Starts the 8 m x 3 m single-ridge Gazebo scene with SLAM Toolbox.  The ridge
is 4.8 m long and the two end headlands are 1.6 m each.  By default the
simulated robot visits both sides and closes the loop at its start point,
saves the Nav2 map and serialized pose graph, and runs offline validators.
--no-drive only checks startup of Gazebo, /scan, /odom and /map.
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
if [[ ! -f "${world_file}" || ! -f "${layout_file}" || ! -f "${slam_params_file}" || ! -f "${layout_validator}" || ! -f "${map_validator}" || ! -f "${farmland_map_validator}" || ! -f "${mapping_driver}" ]]; then
  echo "single-ridge simulation source or validation tool is missing" >&2
  exit 2
fi

python3 "${layout_validator}" --layout "${layout_file}" --world "${world_file}"
mkdir -p "${result_directory}"
{
  date --iso-8601=seconds
  printf 'world=%s\n' "${world_file}"
  printf 'layout=%s\n' "${layout_file}"
  printf 'slam_params=%s\n' "${slam_params_file}"
  printf 'mode=headless_gazebo_slam\n'
  printf 'scene=single_ridge_4.8m_headland_1.6m\n'
  printf 'motion_model=body_forward_with_heading\n'
  printf 'drive=%s\n' "$([[ "${no_drive}" == true ]] && echo false || echo true)"
} > "${result_directory}/metadata.txt"

cleanup() {
  if [[ -n "${launch_pid}" ]]; then
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

  # gazebo_ros can leave gzserver in a separate session.  Match this exact
  # world path so an unrelated Gazebo process is never touched.
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

setsid ros2 launch spore_patrol_sim sim.launch.py \
  world:="${world_file}" \
  spawn_x:=-1.80 \
  spawn_y:=-0.90 \
  spawn_yaw:=0.0 \
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
  echo "PASS single-ridge simulation startup only (no map saved)"
  echo "- results=${result_directory}"
  exit 0
fi

python3 "${mapping_driver}" \
  --speed "${SIM_MAPPING_SPEED:-0.12}" \
  --angular-speed "${SIM_MAPPING_ANGULAR_SPEED:-0.80}" \
  --tolerance "${SIM_MAPPING_TOLERANCE:-0.14}" \
  --heading-tolerance "${SIM_MAPPING_HEADING_TOLERANCE:-0.06}" \
  --segment-timeout "${SIM_MAPPING_SEGMENT_TIMEOUT:-120}" \
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
  --field-length 8.0 \
  --field-width 1.8 \
  --coverage-tolerance 0.10 \
  --min-known-fraction 0.25 \
  --min-occupied-fraction 0.005 \
  > "${result_directory}/map_validation.log"
python3 "${farmland_map_validator}" "${map_base}.yaml" \
  --layout "${layout_file}" \
  --min-row-coverage 0.90 \
  --max-row-spread 0.06 \
  --max-row-offset 0.10 \
  > "${result_directory}/ridge_map_validation.log"

cp "${layout_file}" "${result_directory}/single_ridge_layout.json"
cp "${world_file}" "${result_directory}/single_ridge_8m.world"
cp "${slam_params_file}" "${result_directory}/single_ridge_mapping.yaml"
echo "PASS simulated single-ridge mapping smoke test"
echo "- results=${result_directory}"

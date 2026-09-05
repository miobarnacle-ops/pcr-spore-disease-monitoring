#!/usr/bin/env bash
set -euo pipefail

container_name="humble"

stop_bridge() {
  /usr/bin/docker exec "${container_name}" bash -lc '
    set +e
    for pattern in \
      "[/]opt/ros/humble/bin/ros2 launch rosbridge_server rosbridge_websocket_launch.xml" \
      "[/]opt/ros/humble/lib/rosbridge_server/rosbridge_websocket" \
      "[/]opt/ros/humble/lib/rosapi/rosapi_node"; do
      pgrep -f "${pattern}" | while read -r pid; do kill -TERM "${pid}" 2>/dev/null || true; done
    done
    sleep 2
    for pattern in \
      "[/]opt/ros/humble/lib/rosbridge_server/rosbridge_websocket" \
      "[/]opt/ros/humble/lib/rosapi/rosapi_node"; do
      pgrep -f "${pattern}" | while read -r pid; do kill -KILL "${pid}" 2>/dev/null || true; done
    done
  ' || true
}

if [[ "${1:-}" == "stop" ]]; then
  stop_bridge
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
  # ROS setup scripts reference optional variables while being sourced.
  set -eo pipefail
  source /opt/ros/humble/setup.bash
  source /ws/install/setup.bash
  set -u
  exec ros2 launch rosbridge_server rosbridge_websocket_launch.xml \
    address:=0.0.0.0 \
    port:=9091 \
    call_services_in_new_thread:=true \
    default_call_service_timeout:=5.0 \
    send_action_goals_in_new_thread:=true
'

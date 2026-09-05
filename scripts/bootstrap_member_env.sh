#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "\${BASH_SOURCE[0]}")/.." && pwd)"
echo "PCR member environment bootstrap: \${ROOT_DIR}"

command -v node >/dev/null 2>&1 || { echo "Node.js >=22.13.0 required." >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm required." >&2; exit 1; }
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if (a < 22 || (a === 22 && b < 13)) process.exit(1)'

(cd "\${ROOT_DIR}/spore-monitor-web" && npm ci)

if command -v uv >/dev/null 2>&1; then
  (cd "\${ROOT_DIR}/spore-monitor-web/python-pipeline" && uv sync)
else
  echo "uv not found; install it before using python-pipeline."
fi

if command -v colcon >/dev/null 2>&1 && [ -f /opt/ros/humble/setup.bash ]; then
  echo "ROS 2 Humble detected; build spore-vehicle-nav separately."
else
  echo "ROS 2 Humble not detected; run: cd spore-vehicle-nav && ./verify.sh"
fi


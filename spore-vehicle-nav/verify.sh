#!/usr/bin/env bash
# verify.sh - offline validation for spore-vehicle-nav
# Run after the agent-implemented packages land. No ROS runtime required.
set -u
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "== [1/3] pytest: spore_patrol_route_validation =="
PKG="$REPO_ROOT/src/spore_patrol_route_validation"
if [ -d "$PKG/tests" ]; then
  ( cd "$PKG" && python3 -m pytest tests/ -q )
else
  echo "SKIP: no tests/ in $PKG"
fi

echo
echo
echo "== [2/3] pytest: spore_patrol_gnss =="
GNSS_PKG="$REPO_ROOT/src/spore_patrol_gnss"
if [ -d "$GNSS_PKG/tests" ]; then
  ( cd "$GNSS_PKG" && python3 -m pytest tests/ -q )
  python3 -m py_compile "$GNSS_PKG"/spore_patrol_gnss/*.py "$GNSS_PKG"/launch/*.py
  echo "OK   GNSS Python syntax"
else
  echo "SKIP: no tests/ in $GNSS_PKG"
fi

echo
echo "== [3/3] YAML validation: vehicle packages =="
for f in "$REPO_ROOT"/src/*/config/*.yaml; do
  [ -e "$f" ] || continue
  if python3 -c "import yaml,sys; yaml.safe_load(open('$f'))" 2>/dev/null; then
    echo "OK   $f"
  else
    echo "FAIL $f"
  fi
done

echo
echo "Done. (Full colcon build + on-Pi execution require ROS 2 Humble on the target.)"

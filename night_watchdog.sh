#!/usr/bin/env bash
# 心跳监控: 每5分钟检查主控进程, 崩溃则重启一次
set -u
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGDIR="${LOGDIR:-$ROOT_DIR/night_run_20260814}"
PIDFILE="${PIDFILE:-$ROOT_DIR/night_loop.pid}"
LOOP_SCRIPT="${LOOP_SCRIPT:-$ROOT_DIR/night_loop.sh}"
TS() { date '+%Y-%m-%d %H:%M:%S'; }
END=$(( $(date +%s) + 8*3600 ))
RESTARTED=0
while [ $(date +%s) -lt $END ]; do
  if ! [ -s "$PIDFILE" ] || ! ps -p "$(cat "$PIDFILE")" > /dev/null 2>&1; then
    echo "[$(TS)] 主控进程已死" >> "$LOGDIR/watchdog.log"
    if [ $RESTARTED -eq 0 ]; then
      echo "[$(TS)] 自动重启主控" >> "$LOGDIR/watchdog.log"
      nohup "$LOOP_SCRIPT" > /dev/null 2>&1 &
      echo $! > "$PIDFILE"
      RESTARTED=1
    else
      echo "[$(TS)] 已重启过一次, 不再重启" >> "$LOGDIR/watchdog.log"
      break
    fi
  fi
  sleep 300
done
echo "[$(TS)] watchdog 结束" >> "$LOGDIR/watchdog.log"

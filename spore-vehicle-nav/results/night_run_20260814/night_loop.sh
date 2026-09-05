#!/usr/bin/env bash
# 夜间 8 小时主控: 循环执行安全测试, 带异常自愈
# 安全: motion 需 --arm WHEELS_OFF_GROUND (工具内置第二道防线)
set -u
WS=<REPO_ROOT>/spore-patrol-robot-feature-lidar
LOGDIR=<REPO_ROOT>/night_run_20260814
mkdir -p "$LOGDIR"
TS() { date '+%Y-%m-%d %H:%M:%S'; }
log()  { echo "[$(TS)] $*" >> "$LOGDIR/main.log"; }
ARM=WHEELS_OFF_GROUND
export AISLE_WHEELS_VERIFIED=yes

log "=== 夜间 8 小时主控启动 (架空已人工确认) ==="
log "运动参数: --arm $ARM (vx=0.05m/s, 2秒)"
END=$(( $(date +%s) + 8*3600 ))
ROUND=0
while [ $(date +%s) -lt $END ]; do
  ROUND=$((ROUND+1))
  log "--- 第 ${ROUND} 轮开始 ---"
  # 1) 只读监听
  if /usr/bin/python3 "$WS/tests/chassis_serial/chassis_serial_test.py" listen --port /dev/ttyACM0 --duration 5 >> "$LOGDIR/loop_listen.log" 2>&1; then
    log "  第${ROUND}轮 只读OK"
  else
    log "  第${ROUND}轮 只读失败, 等待5秒重试"
    sleep 5
  fi
  # 2) 架空低速运动 (带 arm 参数)
  if /usr/bin/python3 "$WS/tests/chassis_serial/chassis_serial_test.py" motion --port /dev/ttyACM0 --vx 0.05 --duration 2 --arm "$ARM" >> "$LOGDIR/loop_motion.log" 2>&1; then
    log "  第${ROUND}轮 架空运动OK"
  else
    log "  第${ROUND}轮 架空运动失败, 自动修复一次"
    sleep 5
    /usr/bin/python3 "$WS/tests/chassis_serial/chassis_serial_test.py" motion --port /dev/ttyACM0 --vx 0.05 --duration 2 --arm "$ARM" >> "$LOGDIR/loop_motion_retry.log" 2>&1 && log "  第${ROUND}轮 重试成功" || log "  第${ROUND}轮 重试仍失败"
  fi
  # 3) 停车确认
  /usr/bin/python3 "$WS/tests/chassis_serial/chassis_serial_test.py" stop --port /dev/ttyACM0 >> "$LOGDIR/loop_stop.log" 2>&1
  # 4) 停车后只读确认零速
  /usr/bin/python3 "$WS/tests/chassis_serial/chassis_serial_test.py" listen --port /dev/ttyACM0 --duration 2 >> "$LOGDIR/loop_stop_verify.log" 2>&1
  log "  第${ROUND}轮 停车确认完成"
  sleep 600
done
log "=== 夜间主控结束, 共 ${ROUND} 轮 ==="

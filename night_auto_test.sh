#!/usr/bin/env bash
# ============================================================
# 夜间自动测试计划 (2026-08-14 23:30 ~ 08-15 07:30)
# 负责人: miobarnacle (agent 远程执行)
# 安全铁律: 真实底盘运动测试默认禁用，需 AISLE_WHEELS_VERIFIED=yes 才允许
# ============================================================
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="${WS:-$ROOT_DIR/spore-patrol-robot-feature-lidar}"
LOGDIR="${LOGDIR:-$ROOT_DIR/night_run_20260814}"
mkdir -p "$LOGDIR"
TS() { date '+%Y-%m-%d %H:%M:%S'; }
log()  { echo "[$(TS)] $*" | tee -a "$LOGDIR/main.log"; }

log "=== 夜间自动测试开始 ==="
log "小车架空验证开关: AISLE_WHEELS_VERIFIED=${AISLE_WHEELS_VERIFIED:-no}"
log "真实底盘运动: $([ "${AISLE_WHEELS_VERIFIED:-no}" = "yes" ] && echo 启用 || echo 禁用)"

# ------------------------------------------------------------
# 1. 环境自检
# ------------------------------------------------------------
log "[1] 环境自检"
if /usr/bin/python3 -c "import serial" >/dev/null 2>&1; then
  log "  pyserial OK"
else
  log "  ✗ pyserial 缺失；请由管理员在安全终端安装 python3-serial 后重试"
  exit 1
fi
if ! command -v screen >/dev/null 2>&1; then
  log "  注意：screen 未安装；如当前流程需要，请由管理员在安全终端安装"
fi

# ------------------------------------------------------------
# 2. 离线协议单测 (不依赖小车, 零风险)
# ------------------------------------------------------------
log "[2] 离线协议单元测试"
cd "$WS"
/usr/bin/python3 -m unittest tests/chassis_serial/test_protocol.py -v > "$LOGDIR/unittest.log" 2>&1
if [ $? -eq 0 ]; then log "  ✓ 单测通过 ($(grep -c OK "$LOGDIR/unittest.log") 用例)"; else log "  ✗ 单测失败, 见 unittest.log"; fi

# ------------------------------------------------------------
# 3. 离线现场演练 (fake_stm32 模拟器, 零风险) — 5轮
# ------------------------------------------------------------
log "[3] fake_stm32 模拟器演练"
for i in 1 2 3 4 5; do
  /usr/bin/python3 "$WS/tests/chassis_serial/fake_stm32.py" > /tmp/fake_$i.out 2>&1 &
  FPID=$!
  sleep 2
  PORT=$(grep -oE '/dev/pts/[0-9]+' /tmp/fake_$i.out | head -1)
  if [ -z "$PORT" ]; then log "  ✗ 第${i}轮 模拟器启动失败"; kill $FPID 2>/dev/null; continue; fi
  # 只读监听 3 秒
  if /usr/bin/python3 "$WS/tests/chassis_serial/chassis_serial_test.py" listen --port "$PORT" --duration 3 >> "$LOGDIR/fake_round${i}.log" 2>&1; then
    log "  ✓ 第${i}轮 模拟监听通过 (端口 $PORT)"
  else
    log "  ✗ 第${i}轮 模拟监听失败"
  fi
  kill $FPID 2>/dev/null
  wait $FPID 2>/dev/null
done

# ------------------------------------------------------------
# 4. 真实串口检测 (需要小车 USB 已接)
# ------------------------------------------------------------
log "[4] 真实串口检测"
CHASSIS_PORT=""
for t in 1 2 3 4 5 6 7 8 9 10; do
  P=$(/usr/bin/python3 "$WS/tests/chassis_serial/chassis_serial_test.py" ports 2>/dev/null | grep -oE '/dev/tty(USB|ACM)[0-9]+' | head -1)
  if [ -n "$P" ]; then CHASSIS_PORT=$P; log "  ✓ 第${t}次尝试 发现串口 $P"; break; fi
  log "  第${t}次尝试 未发现串口 (等30s)"
  sleep 30
done

if [ -z "$CHASSIS_PORT" ]; then
  log "  ✗ 整夜未发现小车串口 (小车可能未接线)"
  log "  >>> 跳过真实串口测试, 仅保留离线结果 <<<"
  log "=== 夜间计划结束(未发现小车) ==="
  exit 0
fi

# ------------------------------------------------------------
# 5. 真实串口只读监听 (不动车)
# ------------------------------------------------------------
log "[5] 真实串口只读监听 $CHASSIS_PORT (10秒, 不动车)"
/usr/bin/python3 "$WS/tests/chassis_serial/chassis_serial_test.py" listen --port "$CHASSIS_PORT" --duration 10 > "$LOGDIR/real_listen.log" 2>&1
if [ $? -eq 0 ]; then log "  ✓ 状态帧接收正常 (详见 real_listen.log)"; else log "  ✗ 只读监听失败"; fi

# ------------------------------------------------------------
# 6. 运动测试 — 受严格开关控制
# ------------------------------------------------------------
if [ "${AISLE_WHEELS_VERIFIED:-no}" = "yes" ]; then
  log "[6] 架空低速运动测试 (开关已开启, vx≤0.05, 2秒)"
  /usr/bin/python3 "$WS/tests/chassis_serial/chassis_serial_test.py" motion --port "$CHASSIS_PORT" --vx 0.05 --duration 2 > "$LOGDIR/real_motion.log" 2>&1
  [ $? -eq 0 ] && log "  ✓ 架空低速运动命令发送成功" || log "  ✗ 运动命令失败"
  log "[7] 停车确认 (发送0速)"
  /usr/bin/python3 "$WS/tests/chassis_serial/chassis_serial_test.py" stop --port "$CHASSIS_PORT" > "$LOGDIR/real_stop.log" 2>&1
  [ $? -eq 0 ] && log "  ✓ 停车命令已发送" || log "  ✗ 停车命令失败"
else
  log "[6] 运动测试已跳过 (AISLE_WHEELS_VERIFIED != yes, 车轮架空未人工确认)"
  log "     只读监听结果已保留, 运动测试等白天用户在场确认架空后执行"
fi

# ------------------------------------------------------------
# 7. 汇总
# ------------------------------------------------------------
log "=== 夜间计划结束 ==="
log "日志目录: $LOGDIR"
ls -la "$LOGDIR" >> "$LOGDIR/main.log" 2>&1

# Mock / Replay 数据总线说明

`lib/robot-data-bus.ts` 是远程无实机阶段的任务与遥测入口。它不连接设备、不发布 `/cmd_vel`；数据模式必须显式标记。

| 模式 | 用途 | 数据来源 |
|---|---|---|
| `mock` | 默认开发、演示与故障注入 | 确定性 `MissionSimulator` |
| `replay` | 复现已保存场景，后续可由 rosbag 转换 | 版本化 `robot_replay` JSON |
| `rosbridge` | 只读接收真实车端遥测和任务状态 | `RobotBridge` + `rosbridge-data-adapter`；未连接时明确显示 stale/等待，不发布任务控制 |

## Mock 控制与故障

Mock 支持加载 `route_v1.json`、启动、暂停、恢复、取消和返航。相同路线、起始时间与 `tick` 序列会生成相同任务状态、轨迹和事件。

可注入故障：`disconnect`、`pose_stale`、`pose_jump`、`rtk_degraded`、`low_battery`、`scan_timeout`、`obstacle_stop`、`sampler_busy`、`sampler_failed`、`sampler_timeout`。

- 障碍停车将任务置为 `paused`，不会显示为完成。
- 采样失败/超时将任务置为 `failed` 并携带故障码。
- RTK 降级、低电量和数据过期保持为可见遥测状态，不伪造实机结论。

## Replay 文件与验证

`tests/fixtures/contracts/replay-normal.json` 是最小示例。回放文件必须具有 `contract_version: "1.0"`、`kind: "robot_replay"` 和非空的 `frames`；每帧使用 `INTEGRATION_CONTRACTS.md` 定义的 `mission_status` 与 `robot_telemetry`。

```bash
npm run test:data-bus
```

该测试只证明本地确定性模拟和回放逻辑，不证明 ROS 网络、传感器、RTK 或车辆运动性能。

## rosbridge 静止联调

“机器人监控”页由用户显式连接 `ws://<VEHICLE_HOST>:9091` 后，统一总线可切换到
`rosbridge` 模式。适配器优先使用融合里程计，按照接收时间标记位姿/雷达/诊断新鲜度，
并将车端原生大写任务状态转换为契约中的小写状态。当前未启动路线任务时看到 `idle` 是
正常的；这一步不会自动发布 `/cmd_vel`。

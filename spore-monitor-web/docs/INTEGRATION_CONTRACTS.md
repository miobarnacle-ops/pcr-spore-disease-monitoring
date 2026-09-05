# Web—车辆离线集成接口契约

> 契约版本：`1.0`  
> 生效日期：2026-08-30  
> 范围：本地 Web 控制台、离线 Mock/Replay、rosbridge 适配层与车端状态适配层。  
> 安全边界：本契约描述数据交换，不授权 Web 发布真实运动控制；无实机阶段默认使用 `mock` 或 `replay`，实机阶段的 `rosbridge` 仅接收遥测/任务状态，运动控制仍由独立安全门和用户显式解锁保护。

## 1. 统一信封与关联键

所有任务、事件和遥测对象均必须含有：

```json
{
  "contract_version": "1.0",
  "source_mode": "mock | replay | rosbridge",
  "timestamp_ms": 1777550400000,
  "field_id": "field-demo",
  "mission_id": "mission-demo-001",
  "route_id": "route-demo-001"
}
```

事件和遥测通过 `field_id + mission_id + route_id + sample_id + timestamp_ms` 关联；位姿质量、RTK 状态、诊断等级和采样器状态必须随数据一同输出。`source_mode` 不得省略，避免模拟或回放数据被标记为实测。

## 2. 路线任务

路线文件保持总基线 D1 的文件名约定 `route_v1.json`，冻结字段为：

- `schema_version: "1.0"`
- `frame_id: "field"`
- `coordinate_type: "local_enu"`
- `unit: "m"`

完整字段和车辆限制见 [`ROUTE_SCHEMA.md`](../ROUTE_SCHEMA.md)。该路线被接受后才可生成 `mission_id`；Web 和车端均拒绝未知 schema、坐标系、单位或必填字段。

## 3. 任务状态与事件

控制台规范化状态：`idle`、`loaded`、`running`、`approaching`、`sampling`、`paused`、`returning`、`finished`、`failed`、`cancelled`。

控制台规范化事件：`loaded`、`started`、`waypoint_arrived`、`sampling_started`、`sampling_finished`、`skipped`、`paused`、`resumed`、`returning`、`fault`、`cancelled`。

车端当前状态机的适配映射如下；适配层必须保留原始状态于 `message` 或诊断字段，不能静默丢失：

| 车端状态 | 控制台状态 |
|---|---|
| `IDLE` | `idle` |
| `TASK_LOADED` | `loaded` |
| `NAVIGATING`、`SAMPLE_FINISHED` | `running` |
| `ARRIVED`、`SETTLING`、`SAMPLE_REQUESTED` | `approaching` |
| `SAMPLING` | `sampling` |
| `PAUSED` | `paused` |
| `RETURNING` | `returning` |
| `TASK_FINISHED` | `finished` |
| `STOPPED` | `cancelled` |
| `FAULT` | `failed` |

`PAUSED`、`RETURNING` 已在车辆端纯逻辑状态机中定义；现场远程命令入口尚未冻结，适配层不得把离线状态机能力写成已完成实机远程控制。`skipped`、`resumed` 仍作为扩展事件预留。

## 4. `mission_status` 与 `mission_event`

任务状态示例位于 `tests/fixtures/contracts/mission-status-valid.json`。必填主体字段：

- `state`、`current_waypoint_index`、`current_waypoint_seq`、`sample_id`
- `progress_pct`（0–100）、`eta_s`、`obstacle_stop`
- `fault_code`、`message`

未知状态、缺少关联 ID、进度越界、未来时间戳和过期数据均应被拒绝或标记为不新鲜；过期阈值由数据源配置，不写死到业务计算中。

## 5. `robot_telemetry`

遥测示例位于 `tests/fixtures/contracts/robot-telemetry-valid.json`，包含：

| 范围 | 字段与来源 |
|---|---|
| 融合位姿 | `/odometry/filtered` 为主、`/odom` 仅作降级；包含坐标系、速度、协方差和质量 |
| 雷达 | `/scan` 的新鲜度、前向最小距离和障碍停车标识 |
| 电池 | `/battery_state` 的电压、电量、低电量标识 |
| 诊断 | `/diagnostics` 的等级、消息与超时状态 |
| GNSS/RTK | `/fix` 与适配器生成的 `unavailable/single/float/fix`、差分龄期和卫星数；当前 ATGM336H 只能按普通单点 `single` 接入 |
| 采样器 | `/sampler/status` 的 `unavailable/ready/working/completed/failed/timeout` 与故障码 |

`unavailable` 表示接口尚未接入，不等同于正常或失效；界面必须显式展示。

当前 Web 实现位于 `lib/rosbridge-data-adapter.ts`：它接收 `RobotBridge` 的真实
`/odometry/filtered`、`/odom`、`/scan`、`/battery_state`、`/diagnostics`、
`/mission/status` 和可选 `/gps/status` 数据，完成状态映射、新鲜度计算和前向障碍距离计算。
车端未启动任务时，任务状态显示为 `idle`；未接入采样器时保持 `unavailable`。

## 6. 校验与错误码

Web 实现：`lib/integration-contract.ts`。车端纯逻辑实现：`spore_patrol_route_validation/mission_contract.py`。

两端至少统一处理：`UNSUPPORTED_VERSION`、`INVALID_KIND`、`INVALID_FIELD`、`UNKNOWN_ENUM`，以及数据源层的过期数据。共享 fixtures 的正常、缺字段和未知状态场景必须同时通过/拒绝。

```bash
cd spore-monitor-web && npm run test:contracts
cd ../spore-vehicle-nav && ./verify.sh
```

本契约与适配器已完成离线兼容性验证，并已完成基础 rosbridge 静止实机数据接收验证；
ROS 消息频率、网络延迟、硬件状态、任务执行和车辆安全行为仍需相应实机阶段重新验证。

车端普通 GNSS 适配实现位于 `spore-vehicle-nav/src/spore_patrol_gnss`。它发布 `/fix` 和诊断数据，但不发布 `/cmd_vel`；`single` 仅表示有效的自主 GNSS 解，不表示 RTK 固定解或 `<0.5 m` 精度。

import type {
  MissionEvent,
  MissionEventKind,
  MissionState,
  MissionStatus,
  RobotTelemetry,
} from "./integration-contract";
import type { DataBusSnapshot } from "./robot-data-bus";
import type { RobotStatus } from "./robot-bridge";

/**
 * 将车端 rosbridge 数据映射为 Web 统一任务/遥测契约。
 *
 * 车端 route_tracker 当前发布的是原生 JSON（时间戳为 Unix 秒、状态为
 * 大写枚举），而 Web Mock/Replay 使用的是 versioned contract。适配层把
 * 两者隔离，缺少真实任务、RTK 或采样器话题时明确报告 unavailable，
 * 不伪造“正常”数据。
 */

export interface RosbridgeDataAdapterOptions {
  fieldId?: string;
  missionId?: string;
  routeId?: string;
  poseMaxAgeMs?: number;
  scanMaxAgeMs?: number;
  diagnosticsMaxAgeMs?: number;
  obstacleThresholdM?: number;
}

type NativePayload = Record<string, unknown>;

const DEFAULT_OPTIONS: Required<RosbridgeDataAdapterOptions> = {
  fieldId: "field-live",
  missionId: "mission-live",
  routeId: "route-live",
  poseMaxAgeMs: 1500,
  scanMaxAgeMs: 1000,
  diagnosticsMaxAgeMs: 3000,
  obstacleThresholdM: 0.5,
};

const NATIVE_STATES: Record<string, MissionState> = {
  IDLE: "idle",
  TASK_LOADED: "loaded",
  NAVIGATING: "running",
  ARRIVED: "approaching",
  SETTLING: "approaching",
  SAMPLE_REQUESTED: "approaching",
  SAMPLING: "sampling",
  SAMPLE_FINISHED: "running",
  PAUSED: "paused",
  RETURNING: "returning",
  TASK_FINISHED: "finished",
  STOPPED: "cancelled",
  FAULT: "failed",
};

const EVENT_ALIASES: Record<string, MissionEventKind | null> = {
  started: "started",
  waypoint_arrived: "waypoint_arrived",
  sample_started: "sampling_started",
  sampling_started: "sampling_started",
  sample_finished: "sampling_finished",
  sampling_finished: "sampling_finished",
  paused: "paused",
  resumed: "resumed",
  returning: "returning",
  fault: "fault",
  cancelled: "cancelled",
  stopped: "cancelled",
  state_changed: null,
  task_finished: "sampling_finished",
};

function record(value: unknown): NativePayload | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as NativePayload
    : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function integer(value: unknown): number | null {
  const number = finite(value);
  return number != null && Number.isInteger(number) && number >= 0 ? number : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function boolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function timestampMs(value: unknown, fallback: number) {
  const number = finite(value);
  if (number == null) return fallback;
  // route_tracker publishes time.time() in seconds; canonical Web messages use ms.
  return number < 10_000_000_000 ? number * 1000 : number;
}

function normalizeState(value: unknown): MissionState {
  const raw = text(value);
  if (!raw) return "idle";
  return NATIVE_STATES[raw.toUpperCase()] ?? (Object.values(NATIVE_STATES).includes(raw as MissionState) ? raw as MissionState : "failed");
}

function minForwardRange(status: RobotStatus) {
  const scan = status.scan;
  if (!scan || !scan.ranges.length) return null;
  let minimum = Number.POSITIVE_INFINITY;
  for (let index = 0; index < scan.ranges.length; index += 1) {
    const range = scan.ranges[index];
    if (!Number.isFinite(range) || range < scan.rangeMin || range > scan.rangeMax) continue;
    const angle = scan.angleMin + index * scan.angleIncrement;
    const wrapped = Math.atan2(Math.sin(angle), Math.cos(angle));
    if (Math.abs(wrapped) <= Math.PI / 2) minimum = Math.min(minimum, range);
  }
  return Number.isFinite(minimum) ? minimum : null;
}

function missionMessage(state: MissionState) {
  return {
    idle: "等待车端任务状态",
    loaded: "任务已载入",
    running: "任务运行中",
    approaching: "正在驶向航点",
    sampling: "采样流程中",
    paused: "任务已暂停",
    returning: "正在返航",
    finished: "任务完成",
    failed: "任务故障",
    cancelled: "任务已停止",
  }[state];
}

export class RosbridgeDataAdapter {
  private readonly options: Required<RosbridgeDataAdapterOptions>;
  private status: RobotStatus | null = null;
  private lastPoseRef: RobotStatus["pose"] | null = null;
  private lastScanRef: RobotStatus["scan"] | null = null;
  private lastDiagnosticsRef: RobotStatus["diagnostics"] | null = null;
  private lastPoseAt = 0;
  private lastScanAt = 0;
  private lastDiagnosticsAt = 0;
  private lastGnssAt = 0;
  private gnssState: RobotTelemetry["rtk"] = { state: "unavailable", age_ms: null, satellites: null };
  private mission: MissionStatus;
  private events: MissionEvent[] = [];
  private lastEventKey = "";
  private missionError: string | null = null;

  constructor(options: RosbridgeDataAdapterOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.mission = this.makeIdleMission(Date.now());
  }

  updateRobotStatus(status: RobotStatus, nowMs = Date.now()): DataBusSnapshot {
    if (status.pose !== this.lastPoseRef) {
      this.lastPoseRef = status.pose;
      this.lastPoseAt = nowMs;
    }
    if (status.scan !== this.lastScanRef) {
      this.lastScanRef = status.scan;
      this.lastScanAt = nowMs;
    }
    if (status.diagnostics !== this.lastDiagnosticsRef) {
      this.lastDiagnosticsRef = status.diagnostics;
      this.lastDiagnosticsAt = nowMs;
    }
    this.status = status;
    return this.snapshot(nowMs);
  }

  ingestMissionStatus(payload: unknown, nowMs = Date.now()): DataBusSnapshot {
    let raw: NativePayload | null = null;
    try {
      raw = record(typeof payload === "string" ? JSON.parse(payload) as unknown : payload);
    } catch {
      raw = null;
    }
    if (!raw) {
      this.missionError = "车端 /mission/status 不是有效 JSON。";
      return this.snapshot(nowMs);
    }
    this.missionError = null;
    this.mission = this.mapMission(raw, nowMs);
    this.appendEvent(raw, this.mission);
    return this.snapshot(nowMs);
  }

  ingestGnssStatus(payload: unknown, nowMs = Date.now()): DataBusSnapshot {
    let raw: NativePayload | null = null;
    try {
      raw = record(typeof payload === "string" ? JSON.parse(payload) as unknown : payload);
    } catch {
      raw = null;
    }
    if (!raw) return this.snapshot(nowMs);
    const quality = text(raw.quality)?.toLowerCase();
    const state = quality === "single" || quality === "float" || quality === "fix"
      ? quality
      : "unavailable";
    const valid = raw.fix_valid == null || boolean(raw.fix_valid) !== false;
    this.gnssState = {
      state: valid ? state : "unavailable",
      age_ms: 0,
      satellites: integer(raw.satellites),
    };
    this.lastGnssAt = nowMs;
    return this.snapshot(nowMs);
  }

  snapshot(nowMs = Date.now()): DataBusSnapshot {
    const status = this.status;
    const connected = Boolean(status?.connected);
    const poseFresh = connected && this.lastPoseAt > 0 && nowMs - this.lastPoseAt <= this.options.poseMaxAgeMs;
    const scanFresh = connected && this.lastScanAt > 0 && nowMs - this.lastScanAt <= this.options.scanMaxAgeMs;
    const diagnosticsFresh = connected && this.lastDiagnosticsAt > 0 && nowMs - this.lastDiagnosticsAt <= this.options.diagnosticsMaxAgeMs;
    const minRange = status ? minForwardRange(status) : null;
    const obstacleStop = minRange != null && minRange <= this.options.obstacleThresholdM;
    const diagnostic = status?.diagnostics;
    const diagnosticLevel = diagnostic && Number.isFinite(diagnostic.level)
      ? clamp(Math.round(diagnostic.level), 0, 3) as 0 | 1 | 2 | 3
      : connected ? 1 : 1;
    const diagnosticMessage = this.missionError
      ?? (diagnostic?.message || (connected ? "等待 /diagnostics" : "rosbridge 未连接"));
    const voltage = status && status.battery.voltage > 0 ? status.battery.voltage : null;
    const percentage = voltage != null && Number.isFinite(status?.battery.percentage)
      ? clamp(status?.battery.percentage ?? 0, 0, 100)
      : null;
    const telemetry: RobotTelemetry = {
      contract_version: "1.0",
      kind: "robot_telemetry",
      source_mode: "rosbridge",
      timestamp_ms: nowMs,
      field_id: this.mission.field_id,
      mission_id: this.mission.mission_id,
      route_id: this.mission.route_id,
      pose: {
        frame_id: "odom",
        x_m: status?.pose.x ?? 0,
        y_m: status?.pose.y ?? 0,
        yaw_rad: status?.pose.yaw ?? 0,
        linear_mps: status?.pose.linear ?? 0,
        angular_radps: status?.pose.angular ?? 0,
        covariance_xy_m2: null,
        quality: poseFresh ? diagnosticLevel > 1 ? "degraded" : "good" : "stale",
      },
      scan: {
        fresh: scanFresh,
        age_ms: this.lastScanAt > 0 ? Math.max(0, nowMs - this.lastScanAt) : null,
        min_forward_range_m: minRange,
        obstacle_stop: obstacleStop,
      },
      battery: {
        voltage_v: voltage,
        percentage,
        low: (percentage != null && percentage < 30) || (voltage != null && voltage < 21),
      },
      diagnostics: {
        level: diagnosticLevel,
        message: diagnosticMessage,
        stale: !diagnosticsFresh,
      },
      rtk: connected && this.lastGnssAt > 0
        ? { ...this.gnssState, age_ms: Math.max(0, nowMs - this.lastGnssAt) }
        : { state: "unavailable", age_ms: null, satellites: null },
      sampler: { state: "unavailable", sample_id: this.mission.sample_id, fault_code: null },
    };
    return {
      mode: "rosbridge",
      connected,
      mission: this.mission,
      telemetry,
      events: [...this.events],
    };
  }

  private makeIdleMission(nowMs: number): MissionStatus {
    return {
      contract_version: "1.0",
      kind: "mission_status",
      source_mode: "rosbridge",
      timestamp_ms: nowMs,
      field_id: this.options.fieldId,
      mission_id: this.options.missionId,
      route_id: this.options.routeId,
      state: "idle",
      current_waypoint_index: null,
      current_waypoint_seq: null,
      sample_id: null,
      progress_pct: 0,
      eta_s: null,
      obstacle_stop: false,
      fault_code: null,
      message: "等待车端任务状态",
    };
  }

  private mapMission(raw: NativePayload, nowMs: number): MissionStatus {
    const state = normalizeState(raw.state);
    const waypointIndex = integer(raw.current_waypoint_index ?? raw.waypoint_index);
    const total = integer(raw.total_waypoints);
    const progressValue = finite(raw.progress_pct);
    const progress = progressValue != null
      ? clamp(progressValue, 0, 100)
      : state === "finished"
        ? 100
        : total && total > 1 && waypointIndex != null
          ? clamp(waypointIndex / (total - 1) * 100, 0, 100)
          : 0;
    const fieldId = text(raw.field_id) ?? this.options.fieldId;
    const missionId = text(raw.mission_id) ?? this.options.missionId;
    const routeId = text(raw.route_id) ?? this.options.routeId;
    const nativeState = text(raw.state);
    const obstacle = boolean(raw.obstacle_stop);
    return {
      contract_version: "1.0",
      kind: "mission_status",
      source_mode: "rosbridge",
      timestamp_ms: timestampMs(raw.timestamp_ms ?? raw.timestamp, nowMs),
      field_id: fieldId,
      mission_id: missionId,
      route_id: routeId,
      state,
      current_waypoint_index: waypointIndex,
      current_waypoint_seq: integer(raw.current_waypoint_seq ?? raw.waypoint_seq),
      sample_id: text(raw.sample_id),
      progress_pct: progress,
      eta_s: finite(raw.eta_s),
      obstacle_stop: obstacle ?? false,
      fault_code: text(raw.fault_code) ?? (state === "failed" ? "MISSION_FAULT" : null),
      message: text(raw.message) ?? (nativeState ? `车端状态：${nativeState} · ${missionMessage(state)}` : missionMessage(state)),
    };
  }

  private appendEvent(raw: NativePayload, mission: MissionStatus) {
    const nativeEvent = text(raw.event)?.toLowerCase();
    const event = nativeEvent ? EVENT_ALIASES[nativeEvent] : null;
    if (!event) return;
    const key = `${mission.timestamp_ms}:${event}:${mission.current_waypoint_seq ?? ""}:${mission.sample_id ?? ""}`;
    if (key === this.lastEventKey) return;
    this.lastEventKey = key;
    this.events.push({
      contract_version: "1.0",
      kind: "mission_event",
      source_mode: "rosbridge",
      timestamp_ms: mission.timestamp_ms,
      field_id: mission.field_id,
      mission_id: mission.mission_id,
      route_id: mission.route_id,
      event,
      state: mission.state,
      waypoint_seq: mission.current_waypoint_seq,
      sample_id: mission.sample_id,
      fault_code: mission.fault_code,
      message: mission.message,
    });
    if (this.events.length > 100) this.events.splice(0, this.events.length - 100);
  }
}

export function createRosbridgeSnapshot(status: RobotStatus, nowMs = Date.now(), options?: RosbridgeDataAdapterOptions) {
  const adapter = new RosbridgeDataAdapter(options);
  return adapter.updateRobotStatus(status, nowMs);
}

import type { RouteDocument } from "./route-schema";
import {
  INTEGRATION_CONTRACT_VERSION,
  parseMissionStatus,
  parseRobotTelemetry,
  type MissionEvent,
  type MissionState,
  type MissionStatus,
  type RobotTelemetry,
  type SamplerState,
  type SourceMode,
} from "./integration-contract";

export type FaultInjection = "disconnect" | "pose_stale" | "pose_jump" | "rtk_degraded" | "low_battery" | "scan_timeout" | "obstacle_stop" | "sampler_busy" | "sampler_failed" | "sampler_timeout";

export interface DataBusSnapshot {
  mode: SourceMode;
  connected: boolean;
  mission: MissionStatus;
  telemetry: RobotTelemetry;
  events: MissionEvent[];
}

export interface ReplayFrame {
  at_ms: number;
  mission: MissionStatus;
  telemetry: RobotTelemetry;
  events?: MissionEvent[];
}

export interface ReplayBundle {
  contract_version: typeof INTEGRATION_CONTRACT_VERSION;
  kind: "robot_replay";
  frames: ReplayFrame[];
}

const DEFAULT_TIMESTAMP = 1777550400000;

function round(value: number, digits = 4) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function normalizeMissionState(state: MissionState) {
  return state;
}

/** 可重复的路线任务模拟器；不访问浏览器、网络或系统时间。 */
export class MissionSimulator {
  private timestampMs: number;
  private route: RouteDocument | null = null;
  private fieldId = "field-local";
  private missionId = "mission-local";
  private routeId = "route-local";
  private state: MissionState = "idle";
  private currentIndex = 0;
  private pose = { x: 0, y: 0, yaw: 0, linear: 0, angular: 0 };
  private samplingElapsedMs = 0;
  private faults = new Set<FaultInjection>();
  private events: MissionEvent[] = [];

  constructor(startTimestampMs = DEFAULT_TIMESTAMP, private readonly samplingDurationMs = 2000) {
    this.timestampMs = startTimestampMs;
  }

  load(route: RouteDocument, missionId = `mission-${route.meta.route_id}`) {
    this.route = clone(route);
    this.fieldId = route.meta.field_id;
    this.missionId = missionId;
    this.routeId = route.meta.route_id;
    this.currentIndex = 0;
    const first = route.path[0];
    this.pose = { x: first?.x_m ?? 0, y: first?.y_m ?? 0, yaw: first?.yaw_rad ?? 0, linear: 0, angular: 0 };
    this.state = "loaded";
    this.samplingElapsedMs = 0;
    this.emit("loaded", "任务已载入");
  }

  start() {
    if (this.state !== "loaded" && this.state !== "paused") return;
    const resumed = this.state === "paused";
    this.state = "running";
    this.emit(resumed ? "resumed" : "started", resumed ? "任务已恢复" : "任务已开始");
  }

  pause() {
    if (this.state !== "running" && this.state !== "approaching" && this.state !== "sampling" && this.state !== "returning") return;
    this.state = "paused";
    this.pose.linear = 0;
    this.emit("paused", "任务已暂停");
  }

  resume() {
    if (this.state !== "paused") return;
    this.state = "running";
    this.emit("resumed", "任务已恢复");
  }

  cancel() {
    if (["finished", "failed", "cancelled"].includes(this.state)) return;
    this.state = "cancelled";
    this.pose.linear = 0;
    this.emit("cancelled", "任务已人工取消");
  }

  returnHome() {
    if (!this.route || ["finished", "failed", "cancelled"].includes(this.state)) return;
    this.currentIndex = Math.max(0, this.route.path.length - 1);
    this.state = "returning";
    this.emit("returning", "正在返航");
  }

  setFault(fault: FaultInjection, active: boolean) {
    if (active) this.faults.add(fault); else this.faults.delete(fault);
  }

  reset(startTimestampMs = DEFAULT_TIMESTAMP) {
    this.timestampMs = startTimestampMs;
    this.route = null;
    this.state = "idle";
    this.currentIndex = 0;
    this.pose = { x: 0, y: 0, yaw: 0, linear: 0, angular: 0 };
    this.samplingElapsedMs = 0;
    this.events = [];
    this.faults.clear();
  }

  private waypoint() {
    return this.route?.path[this.currentIndex] ?? null;
  }

  private emit(event: MissionEvent["event"], message: string, faultCode: string | null = null) {
    this.events.push({
      contract_version: INTEGRATION_CONTRACT_VERSION, kind: "mission_event", source_mode: "mock", timestamp_ms: this.timestampMs,
      field_id: this.fieldId, mission_id: this.missionId, route_id: this.routeId, event, state: normalizeMissionState(this.state),
      waypoint_seq: this.waypoint()?.seq ?? null, sample_id: this.waypoint()?.sample_id ?? null, fault_code: faultCode, message,
    });
  }

  tick(deltaMs: number) {
    if (!Number.isFinite(deltaMs) || deltaMs < 0) throw new Error("deltaMs 必须是非负有限数值。");
    this.timestampMs += deltaMs;
    if (!this.route || ["idle", "loaded", "paused", "finished", "failed", "cancelled"].includes(this.state)) return;
    if (this.faults.has("obstacle_stop")) {
      if (this.state !== "paused") { this.state = "paused"; this.pose.linear = 0; this.emit("paused", "前向障碍停车", "OBSTACLE_STOP"); }
      return;
    }
    if (this.state === "sampling") {
      if (this.faults.has("sampler_failed") || this.faults.has("sampler_timeout")) {
        this.state = "failed"; this.pose.linear = 0;
        this.emit("fault", "采样器失败或超时", this.faults.has("sampler_timeout") ? "SAMPLER_TIMEOUT" : "SAMPLER_FAILED");
        return;
      }
      if (this.faults.has("sampler_busy")) return;
      this.samplingElapsedMs += deltaMs;
      if (this.samplingElapsedMs >= this.samplingDurationMs) {
        this.emit("sampling_finished", "采样完成");
        this.samplingElapsedMs = 0;
        this.advanceWaypoint();
      }
      return;
    }
    const target = this.waypoint();
    if (!target) { this.state = "finished"; this.pose.linear = 0; return; }
    const dx = target.x_m - this.pose.x, dy = target.y_m - this.pose.y;
    const distance = Math.hypot(dx, dy);
    const speed = Math.min(target.speed_limit_mps, 0.12);
    const step = speed * deltaMs / 1000;
    if (distance <= Math.max(target.tolerance_m, step)) {
      this.pose = { x: target.x_m, y: target.y_m, yaw: target.yaw_rad ?? this.pose.yaw, linear: 0, angular: 0 };
      this.emit("waypoint_arrived", "到达航点");
      if (target.type === "sampling") {
        this.state = "sampling"; this.samplingElapsedMs = 0; this.emit("sampling_started", "开始采样");
      } else {
        this.advanceWaypoint();
      }
      return;
    }
    const heading = Math.atan2(dy, dx);
    this.pose = { x: round(this.pose.x + Math.cos(heading) * step), y: round(this.pose.y + Math.sin(heading) * step), yaw: heading, linear: speed, angular: 0 };
    this.state = this.state === "returning" ? "returning" : "approaching";
  }

  private advanceWaypoint() {
    if (!this.route) return;
    this.currentIndex += 1;
    if (this.currentIndex >= this.route.path.length) {
      this.currentIndex = Math.max(0, this.route.path.length - 1);
      this.state = "finished"; this.pose.linear = 0; this.emit("sampling_finished", "任务完成");
    } else {
      this.state = "running";
    }
  }

  snapshot(): DataBusSnapshot {
    const waypoint = this.waypoint();
    const progress = this.route?.path.length ? Math.min(100, this.currentIndex / Math.max(1, this.route.path.length - 1) * 100) : 0;
    const failed = this.state === "failed";
    const faultCode = failed ? (this.faults.has("sampler_timeout") ? "SAMPLER_TIMEOUT" : "SAMPLER_FAILED") : this.faults.has("obstacle_stop") ? "OBSTACLE_STOP" : null;
    const poseJump = this.faults.has("pose_jump");
    const samplerState: SamplerState = failed ? (this.faults.has("sampler_timeout") ? "timeout" : "failed") : this.faults.has("sampler_busy") ? "working" : this.state === "sampling" ? "working" : "ready";
    const telemetry: RobotTelemetry = {
      contract_version: INTEGRATION_CONTRACT_VERSION, kind: "robot_telemetry", source_mode: "mock", timestamp_ms: this.timestampMs,
      field_id: this.fieldId, mission_id: this.missionId, route_id: this.routeId,
      pose: { frame_id: "map", x_m: poseJump ? this.pose.x + 30 : this.pose.x, y_m: this.pose.y, yaw_rad: this.pose.yaw, linear_mps: this.pose.linear, angular_radps: this.pose.angular, covariance_xy_m2: this.faults.has("pose_stale") ? null : 0.04, quality: this.faults.has("pose_stale") || poseJump ? "stale" : "good" },
      scan: { fresh: !this.faults.has("scan_timeout"), age_ms: this.faults.has("scan_timeout") ? 5000 : 80, min_forward_range_m: this.faults.has("obstacle_stop") ? 0.35 : 2.5, obstacle_stop: this.faults.has("obstacle_stop") },
      battery: { voltage_v: this.faults.has("low_battery") ? 20.2 : 24.1, percentage: this.faults.has("low_battery") ? 8 : 78, low: this.faults.has("low_battery") },
      diagnostics: { level: failed ? 2 : this.faults.size ? 1 : 0, message: faultCode ?? "OK", stale: this.faults.has("pose_stale") || this.faults.has("scan_timeout") },
      rtk: { state: this.faults.has("rtk_degraded") ? "float" : "unavailable", age_ms: this.faults.has("rtk_degraded") ? 1800 : null, satellites: this.faults.has("rtk_degraded") ? 8 : null },
      sampler: { state: samplerState, sample_id: waypoint?.sample_id ?? null, fault_code: failed ? faultCode : null },
    };
    const mission: MissionStatus = {
      contract_version: INTEGRATION_CONTRACT_VERSION, kind: "mission_status", source_mode: "mock", timestamp_ms: this.timestampMs,
      field_id: this.fieldId, mission_id: this.missionId, route_id: this.routeId, state: this.state,
      current_waypoint_index: this.route ? this.currentIndex : null, current_waypoint_seq: waypoint?.seq ?? null, sample_id: waypoint?.sample_id ?? null,
      progress_pct: round(progress, 2), eta_s: this.route ? Math.max(0, Math.round((this.route.path.length - this.currentIndex) * 10)) : null,
      obstacle_stop: this.faults.has("obstacle_stop"), fault_code: faultCode, message: failed ? "任务失败" : this.state === "finished" ? "任务完成" : "模拟任务运行中",
    };
    return { mode: "mock", connected: !this.faults.has("disconnect"), mission, telemetry, events: clone(this.events) };
  }
}

export class ReplayDataSource {
  private elapsedMs = 0;
  private frames: ReplayFrame[] = [];
  load(bundle: ReplayBundle) {
    if (bundle.contract_version !== INTEGRATION_CONTRACT_VERSION || bundle.kind !== "robot_replay") throw new Error("不支持的回放版本或类型。");
    if (!Array.isArray(bundle.frames) || !bundle.frames.length) throw new Error("回放至少需要一帧。");
    this.frames = bundle.frames.map((frame) => ({ at_ms: frame.at_ms, mission: parseMissionStatus(frame.mission), telemetry: parseRobotTelemetry(frame.telemetry), events: frame.events?.map((event) => event) ?? [] })).sort((a, b) => a.at_ms - b.at_ms);
    this.elapsedMs = 0;
  }
  reset() { this.elapsedMs = 0; }
  tick(deltaMs: number) { this.elapsedMs += Math.max(0, deltaMs); }
  snapshot(): DataBusSnapshot {
    if (!this.frames.length) throw new Error("尚未载入回放。");
    const frame = this.frames.find((item, index) => this.elapsedMs >= item.at_ms && (index === this.frames.length - 1 || this.elapsedMs < this.frames[index + 1].at_ms)) ?? this.frames[0];
    return { mode: "replay", connected: true, mission: { ...frame.mission, source_mode: "replay" }, telemetry: { ...frame.telemetry, source_mode: "replay" }, events: frame.events ?? [] };
  }
}

/** 数据模式总线：Mock/Replay 可离线运行；rosbridge 模式只接收适配层写入的数据。 */
export class RobotDataBus {
  private mode: SourceMode = "mock";
  readonly mock = new MissionSimulator();
  readonly replay = new ReplayDataSource();
  private rosbridgeSnapshot: DataBusSnapshot | null = null;
  setMode(mode: SourceMode) { this.mode = mode; }
  getMode() { return this.mode; }
  tick(deltaMs: number) { if (this.mode === "mock") this.mock.tick(deltaMs); else if (this.mode === "replay") this.replay.tick(deltaMs); }
  setRosbridgeSnapshot(snapshot: DataBusSnapshot) { this.rosbridgeSnapshot = { ...snapshot, mode: "rosbridge" }; }
  snapshot(): DataBusSnapshot {
    if (this.mode === "mock") return this.mock.snapshot();
    if (this.mode === "replay") return this.replay.snapshot();
    if (!this.rosbridgeSnapshot) throw new Error("rosbridge 模式尚未收到有效遥测。");
    return clone(this.rosbridgeSnapshot);
  }
}

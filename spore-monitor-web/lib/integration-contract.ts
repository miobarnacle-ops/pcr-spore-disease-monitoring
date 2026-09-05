/**
 * 本地控制台与车辆侧之间的离线接口契约。
 * 该文件不发起网络连接；rosbridge、Mock 和 Replay 仅负责把各自数据适配为这些对象。
 */

export const INTEGRATION_CONTRACT_VERSION = "1.0" as const;

export type SourceMode = "mock" | "replay" | "rosbridge";
export type MissionState = "idle" | "loaded" | "running" | "approaching" | "sampling" | "paused" | "returning" | "finished" | "failed" | "cancelled";
export type MissionEventKind = "loaded" | "started" | "waypoint_arrived" | "sampling_started" | "sampling_finished" | "skipped" | "paused" | "resumed" | "returning" | "fault" | "cancelled";
export type RtkState = "unavailable" | "single" | "float" | "fix";
export type SamplerState = "unavailable" | "ready" | "working" | "completed" | "failed" | "timeout";

export interface ContractEnvelope {
  contract_version: typeof INTEGRATION_CONTRACT_VERSION;
  source_mode: SourceMode;
  timestamp_ms: number;
  field_id: string;
  mission_id: string;
  route_id: string;
}

export interface MissionStatus extends ContractEnvelope {
  kind: "mission_status";
  state: MissionState;
  current_waypoint_index: number | null;
  current_waypoint_seq: number | null;
  sample_id: string | null;
  progress_pct: number;
  eta_s: number | null;
  obstacle_stop: boolean;
  fault_code: string | null;
  message: string;
}

export interface MissionEvent extends ContractEnvelope {
  kind: "mission_event";
  event: MissionEventKind;
  state: MissionState;
  waypoint_seq: number | null;
  sample_id: string | null;
  fault_code: string | null;
  message: string;
}

export interface RobotTelemetry extends ContractEnvelope {
  kind: "robot_telemetry";
  pose: { frame_id: "map" | "odom"; x_m: number; y_m: number; yaw_rad: number; linear_mps: number; angular_radps: number; covariance_xy_m2: number | null; quality: "good" | "degraded" | "stale" };
  scan: { fresh: boolean; age_ms: number | null; min_forward_range_m: number | null; obstacle_stop: boolean };
  battery: { voltage_v: number | null; percentage: number | null; low: boolean };
  diagnostics: { level: 0 | 1 | 2 | 3; message: string; stale: boolean };
  rtk: { state: RtkState; age_ms: number | null; satellites: number | null };
  sampler: { state: SamplerState; sample_id: string | null; fault_code: string | null };
}

export class ContractValidationError extends Error {
  constructor(public readonly code: string, message: string) { super(message); }
}

type RecordValue = Record<string, unknown>;
const STATES = new Set<MissionState>(["idle", "loaded", "running", "approaching", "sampling", "paused", "returning", "finished", "failed", "cancelled"]);
const EVENTS = new Set<MissionEventKind>(["loaded", "started", "waypoint_arrived", "sampling_started", "sampling_finished", "skipped", "paused", "resumed", "returning", "fault", "cancelled"]);
const SOURCES = new Set<SourceMode>(["mock", "replay", "rosbridge"]);
const RTK_STATES = new Set<RtkState>(["unavailable", "single", "float", "fix"]);
const SAMPLER_STATES = new Set<SamplerState>(["unavailable", "ready", "working", "completed", "failed", "timeout"]);

function record(value: unknown, label: string): RecordValue {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new ContractValidationError("INVALID_OBJECT", `${label} 必须是对象。`);
  return value as RecordValue;
}
function string(value: unknown, label: string, nullable = false): string | null {
  if (nullable && value == null) return null;
  if (typeof value !== "string" || !value) throw new ContractValidationError("INVALID_FIELD", `${label} 必须是非空字符串。`);
  return value;
}
function finite(value: unknown, label: string, nullable = false): number | null {
  if (nullable && value == null) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) throw new ContractValidationError("INVALID_FIELD", `${label} 必须是有限数值。`);
  return value;
}
function boolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new ContractValidationError("INVALID_FIELD", `${label} 必须是布尔值。`);
  return value;
}
function oneOf<T extends string>(value: unknown, values: Set<T>, label: string): T {
  if (typeof value !== "string" || !values.has(value as T)) throw new ContractValidationError("UNKNOWN_ENUM", `${label} 不受支持。`);
  return value as T;
}
function nonNegativeInteger(value: unknown, label: string, nullable = false): number | null {
  const number = finite(value, label, nullable);
  if (number == null) return null;
  if (!Number.isInteger(number) || number < 0) throw new ContractValidationError("INVALID_FIELD", `${label} 必须是非负整数。`);
  return number;
}
function envelope(value: RecordValue): ContractEnvelope {
  const version = string(value.contract_version, "contract_version");
  if (version !== INTEGRATION_CONTRACT_VERSION) throw new ContractValidationError("UNSUPPORTED_VERSION", `不支持契约版本 ${version}。`);
  return {
    contract_version: INTEGRATION_CONTRACT_VERSION,
    source_mode: oneOf(value.source_mode, SOURCES, "source_mode"),
    timestamp_ms: finite(value.timestamp_ms, "timestamp_ms") as number,
    field_id: string(value.field_id, "field_id") as string,
    mission_id: string(value.mission_id, "mission_id") as string,
    route_id: string(value.route_id, "route_id") as string,
  };
}

export function parseMissionStatus(value: unknown): MissionStatus {
  const raw = record(value, "mission_status"); const base = envelope(raw);
  if (raw.kind !== "mission_status") throw new ContractValidationError("INVALID_KIND", "kind 必须为 mission_status。");
  const progress = finite(raw.progress_pct, "progress_pct") as number;
  if (progress < 0 || progress > 100) throw new ContractValidationError("INVALID_FIELD", "progress_pct 必须在 0 到 100 之间。");
  return { ...base, kind: "mission_status", state: oneOf(raw.state, STATES, "state"), current_waypoint_index: nonNegativeInteger(raw.current_waypoint_index, "current_waypoint_index", true), current_waypoint_seq: nonNegativeInteger(raw.current_waypoint_seq, "current_waypoint_seq", true), sample_id: string(raw.sample_id, "sample_id", true), progress_pct: progress, eta_s: finite(raw.eta_s, "eta_s", true), obstacle_stop: boolean(raw.obstacle_stop, "obstacle_stop"), fault_code: string(raw.fault_code, "fault_code", true), message: string(raw.message, "message") as string };
}

export function parseMissionEvent(value: unknown): MissionEvent {
  const raw = record(value, "mission_event"); const base = envelope(raw);
  if (raw.kind !== "mission_event") throw new ContractValidationError("INVALID_KIND", "kind 必须为 mission_event。");
  return { ...base, kind: "mission_event", event: oneOf(raw.event, EVENTS, "event"), state: oneOf(raw.state, STATES, "state"), waypoint_seq: nonNegativeInteger(raw.waypoint_seq, "waypoint_seq", true), sample_id: string(raw.sample_id, "sample_id", true), fault_code: string(raw.fault_code, "fault_code", true), message: string(raw.message, "message") as string };
}

export function parseRobotTelemetry(value: unknown): RobotTelemetry {
  const raw = record(value, "robot_telemetry"); const base = envelope(raw);
  if (raw.kind !== "robot_telemetry") throw new ContractValidationError("INVALID_KIND", "kind 必须为 robot_telemetry。");
  const pose = record(raw.pose, "pose"), scan = record(raw.scan, "scan"), battery = record(raw.battery, "battery"), diagnostics = record(raw.diagnostics, "diagnostics"), rtk = record(raw.rtk, "rtk"), sampler = record(raw.sampler, "sampler");
  const diagnosticLevel = finite(diagnostics.level, "diagnostics.level") as number;
  if (![0, 1, 2, 3].includes(diagnosticLevel)) throw new ContractValidationError("UNKNOWN_ENUM", "diagnostics.level 不受支持。");
  const poseQuality = oneOf(pose.quality, new Set(["good", "degraded", "stale"] as const), "pose.quality");
  const frame = oneOf(pose.frame_id, new Set(["map", "odom"] as const), "pose.frame_id");
  return { ...base, kind: "robot_telemetry", pose: { frame_id: frame, x_m: finite(pose.x_m, "pose.x_m") as number, y_m: finite(pose.y_m, "pose.y_m") as number, yaw_rad: finite(pose.yaw_rad, "pose.yaw_rad") as number, linear_mps: finite(pose.linear_mps, "pose.linear_mps") as number, angular_radps: finite(pose.angular_radps, "pose.angular_radps") as number, covariance_xy_m2: finite(pose.covariance_xy_m2, "pose.covariance_xy_m2", true), quality: poseQuality }, scan: { fresh: boolean(scan.fresh, "scan.fresh"), age_ms: finite(scan.age_ms, "scan.age_ms", true), min_forward_range_m: finite(scan.min_forward_range_m, "scan.min_forward_range_m", true), obstacle_stop: boolean(scan.obstacle_stop, "scan.obstacle_stop") }, battery: { voltage_v: finite(battery.voltage_v, "battery.voltage_v", true), percentage: finite(battery.percentage, "battery.percentage", true), low: boolean(battery.low, "battery.low") }, diagnostics: { level: diagnosticLevel as 0 | 1 | 2 | 3, message: string(diagnostics.message, "diagnostics.message") as string, stale: boolean(diagnostics.stale, "diagnostics.stale") }, rtk: { state: oneOf(rtk.state, RTK_STATES, "rtk.state"), age_ms: finite(rtk.age_ms, "rtk.age_ms", true), satellites: nonNegativeInteger(rtk.satellites, "rtk.satellites", true) }, sampler: { state: oneOf(sampler.state, SAMPLER_STATES, "sampler.state"), sample_id: string(sampler.sample_id, "sampler.sample_id", true), fault_code: string(sampler.fault_code, "sampler.fault_code", true) } };
}

export function isFresh(timestampMs: number, nowMs: number, maxAgeMs: number) {
  return Number.isFinite(timestampMs) && Number.isFinite(nowMs) && Number.isFinite(maxAgeMs) && timestampMs <= nowMs && nowMs - timestampMs <= maxAgeMs;
}

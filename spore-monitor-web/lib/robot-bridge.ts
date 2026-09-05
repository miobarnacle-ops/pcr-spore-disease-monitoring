// 机器人实时数据桥接模块
// 通过 roslibjs 连接 rosbridge_server (WebSocket)，
// 订阅机器人话题(/odom /scan /cmd_vel 等)，供 UI 实时展示。
// 依赖: rosbridge_server 运行在机器人端(或本机仿真)，默认端口 9091。

import { Ros, Topic } from "roslib";

export interface RobotPose {
  x: number;
  y: number;
  yaw: number;
  linear: number;
  angular: number;
}

export interface RobotScan {
  angleMin: number;
  angleMax: number;
  angleIncrement: number;
  ranges: number[];
  rangeMin: number;
  rangeMax: number;
}

export interface RobotBattery {
  voltage: number;
  percentage: number;
}

/** 设备诊断状态（来自 /diagnostics） */
export interface RobotDiagnostics {
  present: boolean;
  level: number;
  message: string;
  values: Record<string, string>;
}

/** 轨迹点：世界坐标(米) + 偏航 + 时间戳(秒)，供导出与回放 */
export interface RobotTrajectoryPoint {
  x: number;
  y: number;
  yaw: number;
  t: number;
}

export interface RobotStatus {
  connected: boolean;
  /** 默认锁定运动，桌面静态测试或未完成安全复核时禁止发布非零速度。 */
  motionEnabled: boolean;
  /** 模拟演示模式：未连接 rosbridge 时生成动态数据流，便于答辩/演示 */
  simulating: boolean;
  simTime: number;
  pose: RobotPose;
  scan: RobotScan | null;
  battery: RobotBattery;
  diagnostics: RobotDiagnostics | null;
  odomHz: number;
  scanHz: number;
  /** 世界坐标 (米) 下的位姿轨迹历史，用于地图叠加、导出与回放 */
  poseHistory: RobotTrajectoryPoint[];
}

export type RobotEventListener = (status: RobotStatus) => void;
export type RobotMissionStatusListener = (payload: string) => void;
export type RobotGnssStatusListener = (payload: string) => void;

/** 实机部署可通过 NEXT_PUBLIC_ROSBRIDGE_URL 覆盖；默认指向车载 Pi。 */
export const DEFAULT_ROSBRIDGE_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_ROSBRIDGE_URL) ||
  "ws://<VEHICLE_HOST>:9091";

interface RosVector3 {
  x?: number;
  y?: number;
  z?: number;
}

interface RosQuaternion {
  x?: number;
  y?: number;
  z?: number;
  w?: number;
}

interface RosOdometryMessage {
  pose?: { pose?: { position?: RosVector3; orientation?: RosQuaternion } };
  twist?: { twist?: { linear?: RosVector3; angular?: RosVector3 } };
}

interface RosLaserScanMessage {
  angle_min?: number;
  angle_max?: number;
  angle_increment?: number;
  ranges?: number[];
  range_min?: number;
  range_max?: number;
}

interface RosBatteryStateMessage {
  voltage?: number;
  percentage?: number;
}

interface RosDiagnosticKeyValue {
  key?: string;
  value?: string;
}

interface RosDiagnosticStatusMessage {
  level?: number;
  message?: string;
  values?: RosDiagnosticKeyValue[];
}

interface RosDiagnosticArrayMessage {
  status?: RosDiagnosticStatusMessage[];
}

class RobotBridge {
  private ros: Ros | null = null;
  private listeners = new Set<RobotEventListener>();
  private missionListeners = new Set<RobotMissionStatusListener>();
  private missionTopic: Topic | null = null;
  private gnssListeners = new Set<RobotGnssStatusListener>();
  private gnssTopic: Topic | null = null;
  private status: RobotStatus = {
    connected: false,
    motionEnabled: false,
    simulating: false,
    simTime: 0,
    pose: { x: 0, y: 0, yaw: 0, linear: 0, angular: 0 },
    scan: null,
    battery: { voltage: 0, percentage: 0 },
    diagnostics: null,
    odomHz: 0,
    scanHz: 0,
    poseHistory: [],
  };
  private lastOdomTime = 0;
  private odomCount = 0;
  private lastFilteredOdomAt = 0;
  private lastScanTime = 0;
  private scanCount = 0;
  private lastTrajectoryPoint: RobotTrajectoryPoint | null = null;
  private poseHistory: RobotTrajectoryPoint[] = [];
  private trajectoryT0 = 0;
  private pulseInterval: ReturnType<typeof setInterval> | null = null;
  private simInterval: ReturnType<typeof setInterval> | null = null;
  private simT = 0;

  getStatus(): RobotStatus {
    return this.status;
  }

  isConnected(): boolean {
    return Boolean(this.ros?.isConnected);
  }

  onStatus(listener: RobotEventListener): () => void {
    this.listeners.add(listener);
    listener(this.status);
    return () => this.listeners.delete(listener);
  }

  /** 订阅车端原生 /mission/status；适配层负责把其 JSON 映射为统一契约。 */
  onMissionStatus(listener: RobotMissionStatusListener): () => void {
    this.missionListeners.add(listener);
    if (this.ros?.isConnected) this.subscribeMissionStatus();
    return () => this.missionListeners.delete(listener);
  }

  private readonly handleMissionStatus = (rawMessage: unknown) => {
    const data = (rawMessage as { data?: unknown })?.data;
    if (typeof data !== "string") return;
    this.missionListeners.forEach((listener) => listener(data));
  };

  private subscribeMissionStatus() {
    if (!this.ros || this.missionTopic || this.missionListeners.size === 0) return;
    this.missionTopic = new Topic({
      ros: this.ros,
      name: "/mission/status",
      messageType: "std_msgs/msg/String",
    });
    this.missionTopic.subscribe(this.handleMissionStatus);
  }

  private clearMissionStatusSubscription() {
    if (!this.missionTopic) return;
    this.missionTopic.unsubscribe(this.handleMissionStatus);
    this.missionTopic = null;
  }

  /** 订阅可选的普通 GNSS/RTK 状态；无该话题时适配层保持 unavailable。 */
  onGnssStatus(listener: RobotGnssStatusListener): () => void {
    this.gnssListeners.add(listener);
    if (this.ros?.isConnected) this.subscribeGnssStatus();
    return () => this.gnssListeners.delete(listener);
  }

  private readonly handleGnssStatus = (rawMessage: unknown) => {
    const data = (rawMessage as { data?: unknown })?.data;
    if (typeof data !== "string") return;
    this.gnssListeners.forEach((listener) => listener(data));
  };

  private subscribeGnssStatus() {
    if (!this.ros || this.gnssTopic || this.gnssListeners.size === 0) return;
    this.gnssTopic = new Topic({
      ros: this.ros,
      name: "/gps/status",
      messageType: "std_msgs/msg/String",
    });
    this.gnssTopic.subscribe(this.handleGnssStatus);
  }

  private clearGnssStatusSubscription() {
    if (!this.gnssTopic) return;
    this.gnssTopic.unsubscribe(this.handleGnssStatus);
    this.gnssTopic = null;
  }

  private emit() {
    this.listeners.forEach((listener) => listener(this.status));
  }

  /** 追加轨迹点：仅在离上一点足够远（≥0.15m）时记录，避免静止时堆点。时间戳以首点为 0。 */
  private pushTrajectory(x: number, y: number, yaw: number) {
    if (this.poseHistory.length === 0) this.trajectoryT0 = Date.now();
    const point: RobotTrajectoryPoint = { x, y, yaw, t: (Date.now() - this.trajectoryT0) / 1000 };
    if (this.lastTrajectoryPoint) {
      const dist = Math.hypot(x - this.lastTrajectoryPoint.x, y - this.lastTrajectoryPoint.y);
      if (dist < 0.15) return;
    }
    this.lastTrajectoryPoint = point;
    this.poseHistory.push(point);
    if (this.poseHistory.length > 4000) this.poseHistory.splice(0, this.poseHistory.length - 4000);
    this.status = { ...this.status, poseHistory: this.poseHistory };
  }

  /** 手动载入历史轨迹（回放/导入用） */
  setPoseHistory(points: RobotTrajectoryPoint[]) {
    this.poseHistory = points;
    this.lastTrajectoryPoint = points.length ? points[points.length - 1] : null;
    this.trajectoryT0 = 0;
    this.status = { ...this.status, poseHistory: this.poseHistory };
    this.emit();
  }

  clearPoseHistory() {
    this.poseHistory = [];
    this.lastTrajectoryPoint = null;
    this.trajectoryT0 = 0;
    this.status = { ...this.status, poseHistory: [] };
    this.emit();
  }

  /** 显式解锁/锁定运动控制。默认锁定，断开连接时也会自动锁定。 */
  setMotionEnabled(enabled: boolean) {
    this.status = { ...this.status, motionEnabled: enabled };
    this.emit();
  }

  connect(url = DEFAULT_ROSBRIDGE_URL): Promise<void> {
    if (this.ros?.isConnected) return Promise.resolve();
    return new Promise((resolve, reject) => {
      this.ros = new Ros({ url });
      const onConnected = () => {
        this.status = { ...this.status, connected: true };
        this.emit();
        this.cleanup();
        this.subscribe();
        this.startPulse();
        resolve();
      };
      const onError = (error: unknown) => {
        this.status = { ...this.status, connected: false, motionEnabled: false };
        this.clearMissionStatusSubscription();
        this.clearGnssStatusSubscription();
        this.emit();
        this.cleanup();
        reject(error instanceof Error ? error : new Error("WebSocket 连接失败"));
      };
      const onClose = () => {
        this.status = { ...this.status, connected: false, motionEnabled: false };
        this.clearMissionStatusSubscription();
        this.clearGnssStatusSubscription();
        this.emit();
        this.cleanup();
      };
      this.cleanup = () => {
        this.ros?.removeListener("connection", onConnected);
        this.ros?.removeListener("error", onError);
        this.ros?.removeListener("close", onClose);
      };
      this.ros.on("connection", onConnected);
      this.ros.on("error", onError);
      this.ros.on("close", onClose);
    });
  }

  private cleanup: () => void = () => {};

  disconnect() {
    this.clearMissionStatusSubscription();
    this.clearGnssStatusSubscription();
    if (this.ros) {
      this.ros.close();
      this.ros = null;
    }
    if (this.pulseInterval) {
      clearInterval(this.pulseInterval);
      this.pulseInterval = null;
    }
    this.status = { ...this.status, connected: false, motionEnabled: false };
    this.emit();
  }

  /** 启动模拟演示模式：未连接 rosbridge 时生成动态位姿/scan/电池数据流 */
  startSimulation() {
    if (this.simInterval) return;
    this.status = { ...this.status, simulating: true };
    this.simT = 0;
    // 模拟初始 scan
    this.status = { ...this.status, scan: this.makeSimScan() };
    this.simInterval = setInterval(() => {
      this.simT += 0.1;
      const t = this.simT;
      // 平滑的矩形路径位姿
      const period = 24;
      const phase = (t % period) / period;
      let x = 0, y = 0, yaw = 0;
      if (phase < 0.25) { x = phase * 4 * 4; yaw = 0; }
      else if (phase < 0.5) { x = 4; y = (phase - 0.25) * 4 * 4; yaw = Math.PI / 2; }
      else if (phase < 0.75) { x = 4 - (phase - 0.5) * 4 * 4; y = 4; yaw = Math.PI; }
      else { x = 0; y = 4 - (phase - 0.75) * 4 * 4; yaw = -Math.PI / 2; }
      const moving = true;
      const linear = moving ? 0.4 : 0;
      this.pushTrajectory(x, y, yaw);
      this.status = {
        ...this.status,
        pose: { x, y, yaw, linear, angular: 0 },
        scan: this.makeSimScan(),
        battery: { voltage: 24.4 - (t % 600) * 0.002, percentage: Math.max(20, 98 - (t % 600) * 0.03) },
        odomHz: 25,
        scanHz: 8,
        simTime: Date.now() / 1000,
      };
      this.emit();
    }, 100);
  }

  private makeSimScan(): RobotScan {
    // 模拟带障碍物轮廓的激光扫描（矩形场 6×6m，四角物体）
    const angleMin = -Math.PI, angleMax = Math.PI, angleIncrement = 2 * Math.PI / 360;
    const ranges: number[] = [];
    for (let i = 0; i < 360; i++) {
      const a = angleMin + i * angleIncrement;
      const wall = 5.5;
      let r = wall;
      // 角落物体
      const cx = 2.2, cy = 2.2;
      const relX = cx * Math.cos(-a) - cy * Math.sin(-a);
      const relY = cx * Math.sin(-a) + cy * Math.cos(-a);
      const objR = relX > 0.1 && Math.abs(relY) < 0.5 ? relX - 0.3 : wall;
      r = Math.min(r, objR);
      ranges.push(Number(r.toFixed(3)));
    }
    return { angleMin, angleMax, angleIncrement, ranges, rangeMin: 0.12, rangeMax: 12 };
  }

  /** 停止模拟演示模式 */
  stopSimulation() {
    if (this.simInterval) {
      clearInterval(this.simInterval);
      this.simInterval = null;
    }
    this.status = { ...this.status, simulating: false };
    this.emit();
  }

  private subscribe() {
    if (!this.ros) return;

    // The fused stream is authoritative when EKF is running. Keep /odom as a
    // fallback for the hardware-only bring-up, without double-counting both
    // streams in the displayed pose and frequency.
    const handleOdometry = (rawMessage: unknown, filtered: boolean) => {
      const now = Date.now();
      if (filtered) this.lastFilteredOdomAt = now;
      else if (now - this.lastFilteredOdomAt < 1500) return;

      const message = rawMessage as RosOdometryMessage;
      const { x = 0, y = 0, z = 0, w = 1 } = message.pose?.pose?.orientation ?? {};
      const position = message.pose?.pose?.position;
      const linear = message.twist?.twist?.linear;
      const angular = message.twist?.twist?.angular;
      const yaw = Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
      this.status = {
        ...this.status,
        pose: {
          x: position?.x ?? 0,
          y: position?.y ?? 0,
          yaw,
          linear: linear?.x ?? 0,
          angular: angular?.z ?? 0,
        },
      };
      const px = position?.x ?? 0;
      const py = position?.y ?? 0;
      this.pushTrajectory(px, py, yaw);
      this.odomCount++;
      if (this.lastOdomTime === 0 || now - this.lastOdomTime >= 2000) {
        this.status.odomHz = this.lastOdomTime === 0 ? Math.max(1, this.odomCount / 2) : this.odomCount / Math.max(1, (now - this.lastOdomTime) / 1000);
        this.odomCount = 0;
        this.lastOdomTime = now;
      }
      this.emit();
    };

    const filteredOdom = new Topic({
      ros: this.ros,
      name: "/odometry/filtered",
      messageType: "nav_msgs/msg/Odometry",
    });
    filteredOdom.subscribe((rawMessage: unknown) => handleOdometry(rawMessage, true));

    const odom = new Topic({
      ros: this.ros,
      name: "/odom",
      messageType: "nav_msgs/msg/Odometry",
    });
    odom.subscribe((rawMessage: unknown) => handleOdometry(rawMessage, false));

    const scan = new Topic({
      ros: this.ros,
      name: "/scan",
      messageType: "sensor_msgs/msg/LaserScan",
    });
    scan.subscribe((rawMessage: unknown) => {
      const message = rawMessage as RosLaserScanMessage;
      this.status = {
        ...this.status,
        scan: {
          angleMin: message.angle_min ?? 0,
          angleMax: message.angle_max ?? 0,
          angleIncrement: message.angle_increment ?? 0,
          ranges: message.ranges ?? [],
          rangeMin: message.range_min ?? 0,
          rangeMax: message.range_max ?? 0,
        },
      };
      const now = Date.now();
      this.scanCount++;
      if (this.lastScanTime === 0 || now - this.lastScanTime >= 2000) {
        this.status.scanHz = this.lastScanTime === 0 ? Math.max(1, this.scanCount / 2) : this.scanCount / Math.max(1, (now - this.lastScanTime) / 1000);
        this.scanCount = 0;
        this.lastScanTime = now;
      }
      this.emit();
    });

    const battery = new Topic({
      ros: this.ros,
      name: "/battery_state",
      messageType: "sensor_msgs/msg/BatteryState",
    });
    battery.subscribe((rawMessage: unknown) => {
      const message = rawMessage as RosBatteryStateMessage;
      const voltage = Number(message.voltage) || 0;
      const percentage = Number(message.percentage);
      // 驱动未填 percentage(NaN)，按 24V 电池近似线性换算
      const pct = Number.isFinite(percentage)
        ? percentage
        : voltage > 0 ? Math.max(0, Math.min(100, ((voltage - 20) / (24.4 - 20)) * 100)) : 0;
      this.status = { ...this.status, battery: { voltage, percentage: Math.round(pct) } };
      this.emit();
    });

    const diagnostics = new Topic({
      ros: this.ros,
      name: "/diagnostics",
      messageType: "diagnostic_msgs/msg/DiagnosticArray",
    });
    diagnostics.subscribe((rawMessage: unknown) => {
      const message = rawMessage as RosDiagnosticArrayMessage;
      const first = message.status?.[0];
      if (!first) return;
      const values: Record<string, string> = {};
      (first.values ?? []).forEach((kv) => { if (kv.key) values[kv.key] = kv.value ?? ""; });
      this.status = {
        ...this.status,
        diagnostics: { present: true, level: first.level ?? 0, message: first.message ?? "", values },
      };
      this.emit();
    });

    this.subscribeMissionStatus();
    this.subscribeGnssStatus();
  }

  private startPulse() {
    if (this.pulseInterval) return;
    this.pulseInterval = setInterval(() => {
      this.status = { ...this.status, simTime: Date.now() / 1000 };
      this.emit();
    }, 1000);
  }

  /** 发布速度指令到 /cmd_vel（远程遥控用） */
  publishCmdVel(linear: number, angular: number) {
    if (!this.ros?.isConnected || !this.status.motionEnabled) return;
    const topic = new Topic({
      ros: this.ros,
      name: "/cmd_vel",
      messageType: "geometry_msgs/msg/Twist",
    });
    topic.publish({
      linear: { x: linear, y: 0, z: 0 },
      angular: { x: 0, y: 0, z: angular },
    });
  }
}

let instance: RobotBridge | null = null;

export function getRobotBridge(): RobotBridge {
  if (!instance) instance = new RobotBridge();
  return instance;
}

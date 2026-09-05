"use client";

import { useEffect, useRef, useState } from "react";
import { useRobotBridge } from "../lib/use-robot-bridge";
import type { SlamMapInfo } from "../lib/slam-map";
import { DEFAULT_ROSBRIDGE_URL, type RobotTrajectoryPoint } from "../lib/robot-bridge";
import type { RouteDocument } from "../lib/route-schema";
import type { SamplingPoint } from "../lib/inspection-engine";
import MissionRuntimePanel from "./mission-runtime-panel";

/** 把 SLAM 地图世界坐标 (米) 换算为地图像素坐标：列=(x-originX)/res，行=height-(y-originY)/res */
function worldToMapPixel(info: SlamMapInfo, x: number, y: number): [number, number] {
  return [
    (x - info.origin[0]) / info.resolution,
    info.height - (y - info.origin[1]) / info.resolution,
  ];
}

function downloadFile(filename: string, content: string, type: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([content], { type }));
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 500);
}

/** 序列化轨迹为 GeoJSON LineString（世界坐标，米） */
function trajectoryToGeoJson(points: RobotTrajectoryPoint[]): string {
  const features: unknown[] = [
    {
      type: "Feature",
      properties: { kind: "robot_trajectory", points: points.length, duration_s: points.length ? points[points.length - 1].t : 0 },
      geometry: {
        type: "LineString",
        coordinates: points.map((p) => [p.x, p.y]),
      },
    },
  ];
  for (let i = 0; i < points.length; i += Math.max(1, Math.floor(points.length / 100))) {
    const p = points[i];
    features.push({
      type: "Feature",
      properties: { kind: "pose_sample", seq: i, t: p.t, yaw: p.yaw },
      geometry: { type: "Point", coordinates: [p.x, p.y] },
    });
  }
  return JSON.stringify({ type: "FeatureCollection", features }, null, 2);
}

/** 轨迹导出 JSON：元数据 + 完整点位 */
function trajectoryToJson(points: RobotTrajectoryPoint[]): string {
  return JSON.stringify(
    {
      version: 1,
      kind: "robot_trajectory",
      generatedAt: new Date().toISOString(),
      count: points.length,
      durationS: points.length ? points[points.length - 1].t : 0,
      points,
    },
    null,
    2,
  );
}

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object";
}

function parseTrajectoryJson(text: string): RobotTrajectoryPoint[] {
  const data: unknown = JSON.parse(text);
  const raw = Array.isArray(data) ? data : isRecord(data) ? data.points : undefined;
  if (!Array.isArray(raw)) throw new Error("轨迹文件缺少 points 数组");
  const points = raw
    .filter(isRecord)
    .map((p) => ({
      x: Number(p.x) || 0,
      y: Number(p.y) || 0,
      yaw: Number(p.yaw) || 0,
      t: Number(p.t) || 0,
    }));
  if (!points.length) throw new Error("轨迹为空");
  return points;
}

function parseTrajectoryGeoJson(text: string): RobotTrajectoryPoint[] {
  const data: unknown = JSON.parse(text);
  if (!isRecord(data) || data.type !== "FeatureCollection" || !Array.isArray(data.features)) throw new Error("不是有效的 GeoJSON");
  const line = data.features.find((feature): feature is UnknownRecord => {
    if (!isRecord(feature) || !isRecord(feature.geometry)) return false;
    return feature.geometry.type === "LineString";
  });
  if (!line || !isRecord(line.geometry) || !Array.isArray(line.geometry.coordinates)) throw new Error("GeoJSON 中没有 LineString 轨迹");
  const coords = line.geometry.coordinates.filter(Array.isArray);
  const points = coords.map((c, i) => ({ x: Number(c[0]) || 0, y: Number(c[1]) || 0, yaw: 0, t: i * 0.1 }));
  if (!points.length) throw new Error("轨迹为空");
  return points;
}

/**
 * 机器人实时轨迹叠加图：以 SLAM 地图为底图，把 /odom 位姿历史
 * （世界坐标系，米）换算到地图像素并绘制为折线。
 * 回放模式（playbackT >= 0）下绘制已回放部分轨迹，并在点间插值当前位置。
 */
function TrajectoryCanvas({ poseHistory, slamInfo, slamImageUrl, current, playbackT }: {
  poseHistory: RobotTrajectoryPoint[];
  slamInfo: SlamMapInfo | null;
  slamImageUrl: string;
  current: { x: number; y: number; yaw: number };
  playbackT: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = 360;
    canvas.height = 280;
    ctx.fillStyle = "#10171c";
    ctx.fillRect(0, 0, 360, 280);

    // 回放模式：定位 playbackT 所在区间并在点间插值位置
    let visibleCount = poseHistory.length;
    let head: RobotTrajectoryPoint | null = null;
    const playing = playbackT >= 0 && poseHistory.length > 0;
    if (playing) {
      let i = 0;
      while (i < poseHistory.length - 1 && poseHistory[i + 1].t <= playbackT) i++;
      visibleCount = i + 1;
      const a = poseHistory[i], b = poseHistory[i + 1];
      if (b && b.t > a.t) {
        const f = Math.max(0, Math.min(1, (playbackT - a.t) / (b.t - a.t)));
        head = { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, yaw: a.yaw + (b.yaw - a.yaw) * f, t: playbackT };
      } else {
        head = a;
      }
    }
    const visibleHistory = playing ? poseHistory.slice(0, visibleCount) : poseHistory;
    const livePose = head ?? (poseHistory.length ? poseHistory[poseHistory.length - 1] : current);

    if (slamInfo && slamImageUrl) {
      const img = new Image();
      img.onload = () => {
        const fit = Math.min(360 / slamInfo.width, 280 / slamInfo.height);
        const dw = slamInfo.width * fit, dh = slamInfo.height * fit;
        const ox = (360 - dw) / 2, oy = (280 - dh) / 2;
        ctx.drawImage(img, ox, oy, dw, dh);
        // 绘制轨迹
        if (visibleHistory.length > 1) {
          ctx.strokeStyle = "#22c7b8";
          ctx.lineWidth = 1.6;
          ctx.beginPath();
          visibleHistory.forEach((p, i) => {
            const [px, py] = worldToMapPixel(slamInfo, p.x, p.y);
            const cx = ox + px * fit, cy = oy + py * fit;
            if (i === 0) ctx.moveTo(cx, cy); else ctx.lineTo(cx, cy);
          });
          ctx.stroke();
        }
        // 当前位置
        const [cpx, cpy] = worldToMapPixel(slamInfo, livePose.x, livePose.y);
        const ccx = ox + cpx * fit, ccy = oy + cpy * fit;
        ctx.fillStyle = "#e1b12c";
        ctx.beginPath();
        ctx.arc(ccx, ccy, 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.fillStyle = "#dbe9ed";
        ctx.font = "10px Microsoft YaHei";
        ctx.textAlign = "left";
        ctx.fillText(`${playing ? "回放" : "轨迹"} ${visibleHistory.length} 点`, 8, 16);
      };
      img.src = slamImageUrl;
      return;
    }

    // 无 SLAM 地图时：自动拟合轨迹范围绘制（世界坐标米）
    ctx.strokeStyle = "rgba(113,128,147,.15)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(180, 140, 20, 0, Math.PI * 2);
    ctx.arc(180, 140, 60, 0, Math.PI * 2);
    ctx.arc(180, 140, 100, 0, Math.PI * 2);
    ctx.stroke();
    // 计算轨迹包围盒，留 20% 边距后适配画布
    const all = poseHistory.length ? poseHistory : [{ x: livePose.x, y: livePose.y } as RobotTrajectoryPoint];
    let minX = livePose.x, maxX = livePose.x, minY = livePose.y, maxY = livePose.y;
    for (const p of all) {
      if (p.x < minX) minX = p.x; if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y; if (p.y > maxY) maxY = p.y;
    }
    const spanX = Math.max(0.8, maxX - minX), spanY = Math.max(0.8, maxY - minY);
    const scale = Math.min((360 * 0.8) / spanX, (280 * 0.8) / spanY);
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    const toCanvas = (x: number, y: number): [number, number] => [
      180 + (x - cx) * scale,
      140 - (y - cy) * scale,
    ];
    if (visibleHistory.length > 1) {
      ctx.strokeStyle = "#22c7b8";
      ctx.lineWidth = 2;
      ctx.beginPath();
      visibleHistory.forEach((p, i) => {
        const [px, py] = toCanvas(p.x, p.y);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
      ctx.stroke();
    }
    const [curPx, curPy] = toCanvas(livePose.x, livePose.y);
    ctx.fillStyle = "#e1b12c";
    ctx.beginPath();
    ctx.arc(curPx, curPy, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = "#dbe9ed";
    ctx.font = "10px Microsoft YaHei";
    ctx.textAlign = "left";
    ctx.fillText(`${playing ? "回放" : "轨迹"} ${visibleHistory.length} 点 · 自动拟合`, 8, 16);
  }, [poseHistory, slamInfo, slamImageUrl, current, playbackT]);
  return <canvas ref={ref} className="lidar-canvas" aria-label="机器人实时轨迹叠加图" data-pts={poseHistory.length} data-mode={slamInfo ? "slam" : "metric"} data-playback={playbackT} />;
}

/** 雷达点云二维可视化（俯视图，机器人位于中心朝右） */
function LidarCanvas({ ranges, angleMin, angleMax, angleIncrement, maxRange }: {
  ranges: number[];
  angleMin: number;
  angleMax: number;
  angleIncrement: number;
  maxRange: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = 280;
    canvas.height = 280;
    ctx.fillStyle = "#10171c";
    ctx.fillRect(0, 0, 280, 280);
    const cx = 140, cy = 140;
    const maxR = maxRange > 0 ? maxRange : 8;
    const scale = 120 / maxR;
    // 网格
    ctx.strokeStyle = "rgba(113,128,147,.14)";
    ctx.lineWidth = 1;
    for (let i = 1; i <= 4; i++) {
      const r = i * 30;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.strokeStyle = "rgba(113,128,147,.08)";
    ctx.beginPath();
    ctx.moveTo(cx, 0); ctx.lineTo(cx, 280);
    ctx.moveTo(0, cy); ctx.lineTo(280, cy);
    ctx.stroke();
    // 点云（俯视：x 向右，y 向上；canvas y 向下翻转）
    const points: [number, number][] = [];
    for (let i = 0; i < ranges.length; i++) {
      const r = ranges[i];
      if (!Number.isFinite(r) || r <= 0.02 || r >= (maxRange > 0 ? maxRange : 8)) continue;
      const angle = angleMin + i * angleIncrement;
      const px = cx + Math.sin(angle) * r * scale;
      const py = cy - Math.cos(angle) * r * scale;
      points.push([px, py]);
    }
    ctx.fillStyle = "#22c7b8";
    for (const [px, py] of points) {
      ctx.fillRect(px, py, 1.4, 1.4);
    }
    // 机器人本体
    ctx.fillStyle = "#e1b12c";
    ctx.beginPath();
    ctx.arc(cx, cy, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#dbe9ed";
    ctx.font = "9px Microsoft YaHei";
    ctx.textAlign = "center";
    ctx.fillText(`${points.length} 点`, cx, 16);
  }, [ranges, angleMin, angleMax, angleIncrement, maxRange]);
  return <canvas ref={ref} className="lidar-canvas" aria-label="激光雷达点云实时视图" />;
}

function PoseIndicator({ x, y, yaw, label }: { x: number; y: number; yaw: number; label: string }) {
  return (
    <div className="pose-chip">
      <b>{label}</b>
      <span>X {x.toFixed(2)} m</span>
      <span>Y {y.toFixed(2)} m</span>
      <span>偏航 {(yaw * 180 / Math.PI).toFixed(1)}°</span>
    </div>
  );
}

function cmdVelRounded(value: number) {
  return Math.abs(value) < 0.001 ? 0 : value;
}

/**
 * 规划 vs 实际轨迹覆盖对比
 * - 规划评估网格(像素) → 米制(×scale 或 ×slamInfo.resolution)
 * - 统计机器人实际轨迹覆盖了多少规划网格点（距离 ≤ 覆盖半径）
 */
function CoverageCompare({ planning, slamInfo, poseHistory }: {
  planning: { evaluationGrid: [number, number][]; gridStepPx: number; coveragePct: number; scale: number } | null;
  slamInfo: SlamMapInfo | null;
  poseHistory: RobotTrajectoryPoint[];
}) {
  if (!planning || !planning.evaluationGrid.length) {
    return <p className="hint">先在「路径规划」运行覆盖路径规划，即可对比规划网格与机器人实际轨迹。</p>;
  }

  // 米制比例尺：优先用 SLAM 分辨率，否则用规划 scale
  const metersPerPx = slamInfo?.resolution ?? (planning.scale > 0 ? 1 / planning.scale : 0.05);
  const gridMeters = planning.evaluationGrid.map(([x, y]) => [x * metersPerPx, y * metersPerPx] as [number, number]);

  // 覆盖半径（米）：网格步长的一半
  const coverRadiusM = Math.max(0.15, planning.gridStepPx * metersPerPx / 2);
  const radiusSq = coverRadiusM * coverRadiusM;

  // 对每个网格点，检查是否有轨迹点在覆盖半径内（采样加速：稀疏轨迹）
  const sample = poseHistory.length > 3000 ? poseHistory.filter((_, i) => i % 5 === 0) : poseHistory;
  let covered = 0;
  const coveredFlags: boolean[] = new Array(gridMeters.length).fill(false);
  for (let gi = 0; gi < gridMeters.length; gi++) {
    const [gx, gy] = gridMeters[gi];
    for (const p of sample) {
      const dx = p.x - gx, dy = p.y - gy;
      if (dx * dx + dy * dy <= radiusSq) { coveredFlags[gi] = true; covered++; break; }
    }
  }
  const actualCoveragePct = gridMeters.length ? (covered / gridMeters.length) * 100 : 0;
  const plannedCoveragePct = planning.coveragePct;
  return (
    <div className="coverage-compare">
      <div className="coverage-bars">
        <div className="cov-row"><span>规划覆盖</span><div className="cov-bar"><i style={{ width: `${Math.min(100, plannedCoveragePct)}%` }} /></div><b>{plannedCoveragePct.toFixed(1)}%</b></div>
        <div className="cov-row"><span>实际覆盖</span><div className="cov-bar actual"><i style={{ width: `${Math.min(100, actualCoveragePct)}%` }} /></div><b>{actualCoveragePct.toFixed(1)}%</b></div>
      </div>
      <div className="cov-stats">
        <span>规划网格 {planning.evaluationGrid.length} 点</span>
        <span>覆盖半径 {coverRadiusM.toFixed(2)}m</span>
        <span>轨迹 {poseHistory.length} 点</span>
        {slamInfo && <span>比例尺 {metersPerPx.toFixed(2)} m/px</span>}
      </div>
      <small className="hint">实际覆盖 = 机器人轨迹进入规划网格点覆盖半径内的比例。规划覆盖是路径规划算法的理论覆盖率。</small>
    </div>
  );
}

export default function RobotMonitorPanel({ initialUrl, slamInfo, slamImageUrl, planning, routeDocument, samples = [] }: {
  initialUrl?: string;
  slamInfo?: SlamMapInfo | null;
  slamImageUrl?: string;
  routeDocument?: RouteDocument | null;
  samples?: SamplingPoint[];
  planning?: {
    evaluationGrid: [number, number][];
    gridStepPx: number;
    coveragePct: number;
    scale: number;
  } | null;
}) {
  const [manualUrl, setManualUrl] = useState(initialUrl ?? DEFAULT_ROSBRIDGE_URL);
  // 实机连接仍由用户显式点击，避免页面加载时意外建立控制链路。
  const robot = useRobotBridge(false, initialUrl ?? DEFAULT_ROSBRIDGE_URL);
  const [vel, setVel] = useState({ linear: 0, angular: 0 });
  const [cmdVel, setCmdVel] = useState({ linear: 0, angular: 0 });
  const [playback, setPlayback] = useState({ playing: false, t: -1, speed: 1 });
  const playbackRef = useRef({ playing: false, t: -1, speed: 1 });
  const playbackRafRef = useRef<number | null>(null);
  const importRef = useRef<HTMLInputElement>(null);

  const { status, connected, connecting, connect, disconnect, setMotionEnabled, publishCmdVel, clearPoseHistory, setPoseHistory, startSimulation, stopSimulation } = robot;
  const scan = status.scan;
  const points = status.poseHistory;
  const duration = points.length ? points[points.length - 1].t : 0;

  const stopPlayback = () => {
    playbackRef.current = { playing: false, t: -1, speed: playbackRef.current.speed };
    setPlayback({ playing: false, t: -1, speed: playbackRef.current.speed });
    if (playbackRafRef.current) { cancelAnimationFrame(playbackRafRef.current); playbackRafRef.current = null; }
  };

  const startPlayback = (fromT = 0) => {
    if (points.length < 2) return;
    stopPlayback();
    playbackRef.current = { playing: true, t: fromT, speed: playbackRef.current.speed || 1 };
    setPlayback({ ...playbackRef.current });
    let last = performance.now();
    const tick = () => {
      const cur = playbackRef.current;
      if (!cur.playing) return;
      const now = performance.now();
      const dt = (now - last) / 1000 * cur.speed;
      last = now;
      let t = cur.t + dt;
      if (t >= duration) {
        t = duration;
        playbackRef.current = { playing: false, t, speed: cur.speed };
        setPlayback({ ...playbackRef.current });
        playbackRafRef.current = null;
        return;
      }
      playbackRef.current = { ...cur, t };
      setPlayback({ ...playbackRef.current });
      playbackRafRef.current = requestAnimationFrame(tick);
    };
    playbackRafRef.current = requestAnimationFrame(tick);
  };

  const togglePlayback = () => {
    if (playbackRef.current.playing) {
      playbackRef.current.playing = false;
      setPlayback({ ...playbackRef.current });
      return;
    }
    if (points.length < 2) return;
    startPlayback(playbackRef.current.t >= 0 ? playbackRef.current.t : 0);
  };

  const handleSpeed = (v: number) => {
    playbackRef.current.speed = v;
    setPlayback({ ...playbackRef.current });
  };

  const seekPlayback = (t: number) => {
    playbackRef.current = { ...playbackRef.current, t };
    setPlayback({ ...playbackRef.current });
  };

  const exportJson = () => {
    if (!points.length) return;
    downloadFile("robot_trajectory.json", trajectoryToJson(points), "application/json");
  };

  const exportGeoJson = () => {
    if (!points.length) return;
    downloadFile("robot_trajectory.geojson", trajectoryToGeoJson(points), "application/geo+json");
  };

  const importTrajectory = async (file?: File) => {
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = file.name.endsWith(".geojson") || file.name.endsWith(".json") && text.includes("FeatureCollection")
        ? parseTrajectoryGeoJson(text)
        : parseTrajectoryJson(text);
      setPoseHistory(parsed);
      stopPlayback();
    } catch (error) {
      alert("轨迹导入失败: " + (error instanceof Error ? error.message : "格式错误"));
    }
  };

  return (
    <>
      <MissionRuntimePanel route={routeDocument ?? null} samples={samples} />
      <section className="control-section">
        <h3>rosbridge 实时桥接（可选）</h3>
        <div className="robot-connect-row">
          <input
            value={manualUrl}
            onChange={(e) => setManualUrl(e.target.value)}
            placeholder={DEFAULT_ROSBRIDGE_URL}
            className="url-input"
          />
          {connected ? (
            <button className="danger" onClick={disconnect}>断开</button>
          ) : (
            <button className="primary" disabled={connecting} onClick={() => connect(manualUrl)}>
              {connecting ? "连接中..." : "连接机器人"}
            </button>
          )}
        </div>
        <div className="button-grid two">
          <button
            className={status.simulating ? "danger" : "primary accent"}
            onClick={() => status.simulating ? stopSimulation() : startSimulation()}
          >
            {status.simulating ? "⏹ 停止模拟数据" : "▶ 模拟数据演示"}
          </button>
        </div>
        <div className={`data-source-chip ${connected ? "live" : status.simulating ? "sim" : ""}`}>
          <i className={connected ? "live" : status.simulating ? "sim" : ""} />
          {connected
            ? "已连接 rosbridge · 实时数据流"
            : status.simulating
              ? "模拟演示模式 · 动态数据流（未连接真车）"
              : "未连接 rosbridge · 离线状态"}
          {status.simTime > 0 && <em>更新时间 {new Date(status.simTime * 1000).toLocaleTimeString("zh-CN")}</em>}
        </div>
      </section>

      {(connected || status.simulating) ? (
        <>
          <div className="stat-strip">
            <span>odom:{status.odomHz.toFixed(1)}Hz</span>
            <span>scan:{status.scanHz.toFixed(1)}Hz</span>
            <span className={status.pose.linear > 0.001 ? "live-text" : ""}>线速:{cmdVelRounded(status.pose.linear).toFixed(2)}m/s</span>
            <span className={status.pose.angular > 0.001 ? "live-text" : ""}>角速:{cmdVelRounded(status.pose.angular).toFixed(2)}rad/s</span>
          </div>

          <section className="control-section">
            <h3>设备状态</h3>
            {status.battery.voltage > 0 ? (
              <div className="battery-panel">
                <div className="battery-bar">
                  <div className="battery-level" style={{ width: `${status.battery.percentage}%`, background: status.battery.percentage < 30 ? "#e1b12c" : "#27ae60" }} />
                </div>
                <div className="battery-meta">
                  <span>电量 {status.battery.percentage}%</span>
                  <span>电压 {status.battery.voltage.toFixed(2)}V</span>
                </div>
              </div>
            ) : (
              <p className="hint">等待 /battery_state 数据...</p>
            )}
            {status.diagnostics && (
              <div className="diag-row">
                <span className={status.diagnostics.level === 0 ? "ok" : "warn"}>{status.diagnostics.level === 0 ? "✓ 正常" : "⚠ 告警"}</span>
                <span>{status.diagnostics.message}</span>
              </div>
            )}
            {status.diagnostics?.values && Object.keys(status.diagnostics.values).length > 0 && (
              <div className="diag-values">
                {Object.entries(status.diagnostics.values).slice(0, 8).map(([k, v]) => (
                  <span key={k}>{k}: <b>{v}</b></span>
                ))}
              </div>
            )}
          </section>

          <section className="control-section">
            <h3>实时位置</h3>
            <PoseIndicator x={status.pose.x} y={status.pose.y} yaw={status.pose.yaw} label="当前位姿" />
          </section>

          <section className="control-section">
            <h3>轨迹叠加 {slamInfo ? "· SLAM 地图" : "· 米制坐标"}</h3>
            <TrajectoryCanvas
              poseHistory={points}
              slamInfo={slamInfo ?? null}
              slamImageUrl={slamImageUrl ?? ""}
              current={{ x: status.pose.x, y: status.pose.y, yaw: status.pose.yaw }}
              playbackT={playback.t}
            />
            <div className="button-grid two">
              <button onClick={() => { clearPoseHistory(); stopPlayback(); }}>清空轨迹</button>
              <button onClick={exportJson}>导出轨迹 JSON</button>
              <button onClick={exportGeoJson}>导出 GeoJSON</button>
              <button onClick={() => importRef.current?.click()}>导入轨迹</button>
            </div>
            <input ref={importRef} hidden type="file" accept=".json,.geojson,application/json,application/geo+json" onChange={(e) => importTrajectory(e.target.files?.[0])} />
            <div className="playback-row">
              <button className="primary" onClick={togglePlayback} disabled={points.length < 2}>
                {playback.playing ? "⏸ 暂停" : "▶ 回放"}
              </button>
              <button onClick={stopPlayback}>⏹ 停止</button>
              <span>倍速</span>
              <select value={playback.speed} onChange={(e) => handleSpeed(Number(e.target.value))}>
                <option value="0.5">0.5×</option>
                <option value="1">1×</option>
                <option value="2">2×</option>
                <option value="4">4×</option>
                <option value="8">8×</option>
              </select>
            </div>
            <input type="range" min="0" max={duration} step="0.01" value={Math.max(0, Math.min(playback.t >= 0 ? playback.t : 0, duration))} onChange={(e) => seekPlayback(Number(e.target.value))} className="playback-slider" aria-label="回放进度" />
            <small className="hint">
              {playback.t >= 0
                ? `回放进度 t=${playback.t.toFixed(1)}s / ${duration.toFixed(1)}s · ${points.length} 点`
                : points.length ? `${points.length} 点 · ${duration.toFixed(1)}s · 点击回放查看轨迹动画` : "驱动机器人或导入轨迹后，可导出与回放"}
            </small>
            <small className="hint">{slamInfo ? `地图 ${slamInfo.width}×${slamInfo.height}px @ ${slamInfo.resolution} m/px，轨迹为世界坐标(m)实时换算` : "可在「路径规划」导入 SLAM 地图后，轨迹将叠加到真实地图底图"}</small>
          </section>

          <section className="control-section">
            <h3>规划 vs 实际覆盖</h3>
            <CoverageCompare planning={planning ?? null} slamInfo={slamInfo ?? null} poseHistory={points} />
          </section>

          <section className="control-section">
            <h3>激光雷达 /scan</h3>
            {scan ? (
              <div className="lidar-row">
                <LidarCanvas
                  ranges={scan.ranges}
                  angleMin={scan.angleMin}
                  angleMax={scan.angleMax}
                  angleIncrement={scan.angleIncrement}
                  maxRange={scan.rangeMax}
                />
                <div className="lidar-meta">
                  <span>测量点: {scan.ranges.length}</span>
                  <span>范围: {scan.rangeMin.toFixed(2)}~{scan.rangeMax.toFixed(2)}m</span>
                  <span>角度: {(scan.angleMin * 180 / Math.PI).toFixed(0)}°~{(scan.angleMax * 180 / Math.PI).toFixed(0)}°</span>
                  <span>更新率: {status.scanHz.toFixed(1)}Hz</span>
                </div>
              </div>
            ) : (
              <p className="hint">等待 /scan 数据...</p>
            )}
          </section>

          <section className="control-section">
            <h3>视频监控 {status.simulating ? "· 模拟" : "· 占位"}</h3>
            <div className="video-placeholder">
              <div className="video-placeholder-inner">
                <span className="video-cam-icon">📷</span>
                <p>摄像头实时画面</p>
                <small>ROS 端接入 /image_raw 或 RTSP 流后在此显示</small>
                <span className="video-status">未接入视频源</span>
              </div>
            </div>
            <div className="video-info-row">
              <span>视频源: 未配置</span>
              <span>帧率: -- fps</span>
              <span>分辨率: --×--</span>
            </div>
            <small className="hint">支持通过 rosbridge 订阅 /image_raw（sensor_msgs/Image）或配置 RTSP 地址实现实时回传，满足“高清视频监控实时回传”需求。</small>
          </section>

          <section className="control-section">
            <h3>远程遥控 /cmd_vel</h3>
            <div className={`data-source-chip ${status.motionEnabled ? "live" : ""}`}>
              <i className={status.motionEnabled ? "live" : "sim"} />
              {status.motionEnabled ? "运动控制已解锁" : "运动控制已锁定（桌面静态测试）"}
            </div>
            {status.simulating && <small className="hint" style={{ display: "block" }}>模拟模式下仅展示数据流，不发送真实运动指令。</small>}
            <button
              className={status.motionEnabled ? "danger" : "primary"}
              onClick={() => {
                if (!status.motionEnabled && !window.confirm("确认车辆已落地、区域清空且急停人员就位？")) return;
                setMotionEnabled(!status.motionEnabled);
                setCmdVel({ linear: 0, angular: 0 });
                setVel({ linear: 0, angular: 0 });
              }}
            >
              {status.motionEnabled ? "锁定运动控制" : "解锁运动控制"}
            </button>
            <div className="vel-input-row">
              <label className="field-row">
                <span>线速度</span>
                <div><input type="number" step="0.05" min={-0.5} max={0.5} value={vel.linear} onChange={(e) => setVel({ ...vel, linear: Number(e.target.value) })} /><em>m/s</em></div>
              </label>
              <label className="field-row">
                <span>角速度</span>
                <div><input type="number" step="0.1" min={-1} max={1} value={vel.angular} onChange={(e) => setVel({ ...vel, angular: Number(e.target.value) })} /><em>rad/s</em></div>
              </label>
            </div>
            <div className="button-grid two">
              <button className="primary" disabled={!status.motionEnabled || status.simulating} onClick={() => { publishCmdVel(vel.linear, vel.angular); setCmdVel(vel); }}>发送速度指令</button>
              <button className="danger" onClick={() => { publishCmdVel(0, 0); setMotionEnabled(false); setCmdVel({ linear: 0, angular: 0 }); setVel({ linear: 0, angular: 0 }); }}>软件停车并锁定</button>
            </div>
            <p className="hint">已发送: 线 {cmdVelRounded(cmdVel.linear).toFixed(2)} m/s · 角 {cmdVelRounded(cmdVel.angular).toFixed(2)} rad/s</p>
          </section>
        </>
      ) : (
        <p className="hint">统一任务面板支持离线 Mock/Replay，也可切换为 rosbridge 实机遥测。连接由用户显式发起，本页面不自动发布任务控制；运动控制默认锁定。</p>
      )}
    </>
  );
}

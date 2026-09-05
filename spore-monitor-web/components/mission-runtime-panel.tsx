"use client";

import { useRef, useState } from "react";
import type { RouteDocument } from "../lib/route-schema";
import type { SamplingPoint } from "../lib/inspection-engine";
import type { FaultInjection, ReplayBundle } from "../lib/robot-data-bus";
import { useRobotDataBus } from "../lib/use-robot-data-bus";

const FAULTS: Array<{ fault: FaultInjection; label: string }> = [
  { fault: "disconnect", label: "断联" }, { fault: "pose_stale", label: "位姿超时" }, { fault: "pose_jump", label: "位姿跳变" },
  { fault: "rtk_degraded", label: "RTK降级" }, { fault: "low_battery", label: "低电量" }, { fault: "scan_timeout", label: "雷达超时" },
  { fault: "obstacle_stop", label: "障碍停车" }, { fault: "sampler_busy", label: "采样器忙" }, { fault: "sampler_failed", label: "采样失败" }, { fault: "sampler_timeout", label: "采样超时" },
];

export default function MissionRuntimePanel({ route, samples }: { route: RouteDocument | null; samples: SamplingPoint[] }) {
  const runtime = useRobotDataBus();
  const [activeFaults, setActiveFaults] = useState<Set<FaultInjection>>(new Set());
  const replayInput = useRef<HTMLInputElement>(null);
  const snapshot = runtime.snapshot;
  const mission = snapshot?.mission;
  const telemetry = snapshot?.telemetry;
  const sample = mission?.sample_id ? samples.find((item) => item.point_id === mission.sample_id) : null;
  const mode = snapshot?.mode ?? "rosbridge";

  const toggleFault = (fault: FaultInjection) => {
    const next = new Set(activeFaults);
    if (next.has(fault)) next.delete(fault); else next.add(fault);
    setActiveFaults(next); runtime.injectFault(fault, next.has(fault));
  };
  const loadReplay = async (file?: File) => {
    if (!file) return;
    try { runtime.loadReplay(JSON.parse(await file.text()) as ReplayBundle); }
    catch (error) { alert(`回放载入失败：${error instanceof Error ? error.message : "格式错误"}`); }
  };

  return <section className="control-section mission-runtime" data-source-mode={mode}>
    <h3>任务与遥测总线</h3>
    <div className={`data-source-chip ${mode === "rosbridge" ? "live" : "sim"}`}>
      <i className={mode === "rosbridge" ? "live" : "sim"} />
      {mode === "mock" ? "模拟数据 · 不连接实机" : mode === "replay" ? "回放数据 · 只读" : snapshot?.connected ? "rosbridge 实机遥测" : "rosbridge · 等待实机连接"}
      {mission && <em>{mission.message}</em>}
    </div>
    <div className="button-grid three">
      <button className={mode === "mock" ? "primary" : ""} onClick={() => runtime.setMode("mock")}>Mock</button>
      <button className={mode === "replay" ? "primary" : ""} onClick={() => replayInput.current?.click()}>载入回放</button>
      <button className={mode === "rosbridge" ? "primary" : ""} onClick={() => runtime.setMode("rosbridge")}>rosbridge</button>
    </div>
    <input ref={replayInput} hidden type="file" accept="application/json,.json" onChange={(event) => loadReplay(event.target.files?.[0])} />
    {runtime.error && <p className="hint">{runtime.error}</p>}
    {mode === "rosbridge" && <p className="hint">请先在下方“rosbridge 实时桥接”区域连接机器人；任务状态来自车端 `/mission/status`，未启动路线任务时显示空闲。</p>}
    <div className="button-grid three">
      <button disabled={!route || mode !== "mock"} onClick={() => route && runtime.loadRoute(route, `mission-${route.meta.route_id}`)}>载入规划任务</button>
      <button className="primary" disabled={mode !== "mock" || !mission || !["loaded", "paused"].includes(mission.state)} onClick={() => mission?.state === "paused" ? runtime.resume() : runtime.start()}>{mission?.state === "paused" ? "继续模拟" : "启动模拟"}</button>
      <button disabled={mode !== "mock"} onClick={() => runtime.pause()}>暂停</button>
      <button disabled={mode !== "mock"} onClick={() => runtime.returnHome()}>返航</button>
      <button className="danger" disabled={mode !== "mock"} onClick={() => runtime.cancel()}>取消任务</button>
      <button disabled={mode !== "mock"} onClick={() => { setActiveFaults(new Set()); runtime.reset(); }}>重置</button>
    </div>
    <div className="playback-row"><span>模拟/回放倍速</span><select value={runtime.speed} onChange={(event) => runtime.setSpeed(Number(event.target.value))}><option value="0.5">0.5×</option><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select></div>
    {mission && telemetry && <>
      <div className="result-grid mission-grid">
        <b>任务状态</b><span>{mission.state}</span><b>进度</b><span>{mission.progress_pct.toFixed(1)}%</span>
        <b>航点</b><span>{mission.current_waypoint_seq ?? "--"}</span><b>ETA</b><span>{mission.eta_s == null ? "--" : `${mission.eta_s}s`}</span>
        <b>RTK</b><span>{telemetry.rtk.state}</span><b>采样器</b><span>{telemetry.sampler.state}</span>
        <b>诊断</b><span>{telemetry.diagnostics.message}</span><b>数据源</b><span>{mode}</span>
      </div>
      <small className="hint">当前 sample_id：{mission.sample_id ?? "--"}{sample ? ` · PCR ${sample.pcr_verdict || "待检测"} · 风险 ${sample.risk}` : ""}</small>
      <div className="fault-grid">{FAULTS.map(({ fault, label }) => <button key={fault} className={activeFaults.has(fault) ? "danger" : ""} disabled={mode !== "mock"} onClick={() => toggleFault(fault)}>{label}</button>)}</div>
      <div className="event-timeline">{snapshot.events.slice(-6).reverse().map((event, index) => <small key={`${event.timestamp_ms}-${index}`}>{event.event} · {event.state}{event.sample_id ? ` · ${event.sample_id}` : ""}{event.fault_code ? ` · ${event.fault_code}` : ""}</small>)}</div>
      <small className="hint">“障碍停车”是模拟软件状态，不是物理急停；实机安全操作仍以物理急停和现场流程为准。</small>
    </>}
  </section>;
}

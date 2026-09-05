"use client";

import { useEffect, useMemo, useState } from "react";
import type { RouteDocument } from "./route-schema";
import { RobotDataBus, type DataBusSnapshot, type FaultInjection, type ReplayBundle } from "./robot-data-bus";
import type { SourceMode } from "./integration-contract";
import { RosbridgeDataAdapter } from "./rosbridge-data-adapter";
import { getRobotBridge } from "./robot-bridge";

const bus = new RobotDataBus();
const bridge = getRobotBridge();
const rosbridgeAdapter = new RosbridgeDataAdapter();
let adapterAttached = false;

function readSnapshot(): { snapshot: DataBusSnapshot | null; error: string | null } {
  try { return { snapshot: bus.snapshot(), error: null }; }
  catch (error) { return { snapshot: null, error: error instanceof Error ? error.message : String(error) }; }
}

function attachRosbridgeAdapter() {
  if (adapterAttached) return;
  adapterAttached = true;
  bridge.onStatus((status) => bus.setRosbridgeSnapshot(rosbridgeAdapter.updateRobotStatus(status)));
  bridge.onMissionStatus((payload) => bus.setRosbridgeSnapshot(rosbridgeAdapter.ingestMissionStatus(payload)));
  bridge.onGnssStatus((payload) => bus.setRosbridgeSnapshot(rosbridgeAdapter.ingestGnssStatus(payload)));
}

/** 本地任务总线 React 适配；rosbridge 仅接收遥测/任务状态，不发布 ROS 控制话题。 */
export function useRobotDataBus() {
  const [view, setView] = useState(readSnapshot);
  const [speed, setSpeed] = useState(1);
  const refresh = () => setView(readSnapshot());

  useEffect(() => {
    attachRosbridgeAdapter();
    const timer = window.setInterval(() => { bus.tick(100 * speed); refresh(); }, 100);
    return () => window.clearInterval(timer);
  }, [speed]);

  return useMemo(() => ({
    ...view,
    speed,
    setSpeed,
    setMode: (mode: SourceMode) => { attachRosbridgeAdapter(); bus.setMode(mode); refresh(); },
    loadRoute: (route: RouteDocument, missionId?: string) => { bus.setMode("mock"); bus.mock.load(route, missionId); refresh(); },
    reset: () => { bus.setMode("mock"); bus.mock.reset(); refresh(); },
    start: () => { bus.mock.start(); refresh(); },
    pause: () => { bus.mock.pause(); refresh(); },
    resume: () => { bus.mock.resume(); refresh(); },
    cancel: () => { bus.mock.cancel(); refresh(); },
    returnHome: () => { bus.mock.returnHome(); refresh(); },
    injectFault: (fault: FaultInjection, active: boolean) => { bus.mock.setFault(fault, active); refresh(); },
    loadReplay: (bundle: ReplayBundle) => { bus.replay.load(bundle); bus.setMode("replay"); refresh(); },
  }), [speed, view]);
}

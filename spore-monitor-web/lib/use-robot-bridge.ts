"use client";

import { useEffect, useState } from "react";
import { DEFAULT_ROSBRIDGE_URL, getRobotBridge, type RobotStatus, type RobotTrajectoryPoint } from "./robot-bridge";

const bridge = getRobotBridge();

export interface RobotBridgeState {
  status: RobotStatus;
  connected: boolean;
  connecting: boolean;
  connect: (url?: string) => Promise<void>;
  disconnect: () => void;
  setMotionEnabled: (enabled: boolean) => void;
  publishCmdVel: (linear: number, angular: number) => void;
  clearPoseHistory: () => void;
  setPoseHistory: (points: RobotTrajectoryPoint[]) => void;
  startSimulation: () => void;
  stopSimulation: () => void;
}

/** React hook：订阅机器人实时状态（rosbridge）。页面挂载后自动连接默认地址。 */
export function useRobotBridge(autoConnect = true, url = DEFAULT_ROSBRIDGE_URL): RobotBridgeState {
  const [connected, setConnected] = useState(() => bridge.isConnected());
  const [connecting, setConnecting] = useState(() => autoConnect && !bridge.isConnected());
  const [status, setStatus] = useState<RobotStatus>(() => bridge.getStatus());

  useEffect(() => {
    const unsubscribe = bridge.onStatus((next) => {
      setStatus(next);
      setConnected(next.connected);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (autoConnect) {
      if (!bridge.isConnected()) {
        bridge.connect(url).catch(() => {}).finally(() => setConnecting(false));
      }
    }
  }, [autoConnect, url]);

  const connect = (nextUrl?: string) => {
    setConnecting(true);
    return bridge.connect(nextUrl ?? url).finally(() => setConnecting(false));
  };

  const disconnect = () => bridge.disconnect();
  const setMotionEnabled = (enabled: boolean) => bridge.setMotionEnabled(enabled);
  const publishCmdVel = (linear: number, angular: number) => bridge.publishCmdVel(linear, angular);
  const clearPoseHistory = () => bridge.clearPoseHistory();
  const setPoseHistory = (points: RobotTrajectoryPoint[]) => bridge.setPoseHistory(points);
  const startSimulation = () => bridge.startSimulation();
  const stopSimulation = () => bridge.stopSimulation();

  return { status, connected, connecting, connect, disconnect, setMotionEnabled, publishCmdVel, clearPoseHistory, setPoseHistory, startSimulation, stopSimulation };
}

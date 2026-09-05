import assert from "node:assert/strict";
import { test } from "node:test";
import { RosbridgeDataAdapter } from "../../lib/rosbridge-data-adapter";
import type { RobotStatus } from "../../lib/robot-bridge";

function status(overrides: Partial<RobotStatus> = {}): RobotStatus {
  return {
    connected: true,
    motionEnabled: false,
    simulating: false,
    simTime: 0,
    pose: { x: 1.2, y: -0.4, yaw: 0.5, linear: 0.02, angular: -0.01 },
    scan: {
      angleMin: -Math.PI,
      angleMax: Math.PI,
      angleIncrement: Math.PI / 2,
      ranges: [4, 4, 0.4, 4, 4],
      rangeMin: 0.12,
      rangeMax: 8,
    },
    battery: { voltage: 23.7, percentage: 80 },
    diagnostics: { present: true, level: 0, message: "OK", values: {} },
    odomHz: 20,
    scanHz: 11,
    poseHistory: [],
    ...overrides,
  };
}

test("maps live robot status into a validated rosbridge telemetry snapshot", () => {
  const adapter = new RosbridgeDataAdapter();
  const snapshot = adapter.updateRobotStatus(status(), 1000);

  assert.equal(snapshot.mode, "rosbridge");
  assert.equal(snapshot.connected, true);
  assert.equal(snapshot.telemetry.pose.frame_id, "odom");
  assert.equal(snapshot.telemetry.pose.x_m, 1.2);
  assert.equal(snapshot.telemetry.pose.quality, "good");
  assert.equal(snapshot.telemetry.scan.min_forward_range_m, 0.4);
  assert.equal(snapshot.telemetry.scan.obstacle_stop, true);
  assert.equal(snapshot.telemetry.battery.voltage_v, 23.7);
  assert.equal(snapshot.telemetry.rtk.state, "unavailable");
  assert.equal(snapshot.telemetry.sampler.state, "unavailable");
});

test("maps native route tracker state and events without exposing uppercase enums", () => {
  const adapter = new RosbridgeDataAdapter({ fieldId: "field-a", missionId: "mission-a", routeId: "route-a" });
  adapter.updateRobotStatus(status(), 2000);
  const snapshot = adapter.ingestMissionStatus(JSON.stringify({
    event: "sampling_started",
    state: "SAMPLING",
    waypoint_index: 2,
    waypoint_seq: 7,
    total_waypoints: 5,
    sample_id: "R1-P2",
    timestamp: 1.5,
  }), 3000);

  assert.equal(snapshot.mission.state, "sampling");
  assert.equal(snapshot.mission.current_waypoint_index, 2);
  assert.equal(snapshot.mission.current_waypoint_seq, 7);
  assert.equal(snapshot.mission.progress_pct, 50);
  assert.equal(snapshot.mission.timestamp_ms, 1500);
  assert.equal(snapshot.mission.sample_id, "R1-P2");
  assert.equal(snapshot.events.at(-1)?.event, "sampling_started");
  assert.equal(snapshot.events.at(-1)?.state, "sampling");
});

test("maps the ATGM336H status topic to single GNSS without upgrading it to RTK fix", () => {
  const adapter = new RosbridgeDataAdapter();
  adapter.updateRobotStatus(status(), 4000);
  const snapshot = adapter.ingestGnssStatus(JSON.stringify({
    source: "ATGM336H",
    quality: "single",
    fix_valid: true,
    satellites: 9,
    timestamp_ms: 4000,
  }), 4100);

  assert.equal(snapshot.telemetry.rtk.state, "single");
  assert.equal(snapshot.telemetry.rtk.satellites, 9);
  assert.equal(snapshot.telemetry.rtk.age_ms, 0);
  assert.notEqual(snapshot.telemetry.rtk.state, "fix");
});

test("disconnects and malformed mission payloads are visibly stale instead of normal", () => {
  const adapter = new RosbridgeDataAdapter();
  adapter.updateRobotStatus(status(), 1000);
  const disconnected = adapter.updateRobotStatus(status({ connected: false }), 3000);
  assert.equal(disconnected.connected, false);
  assert.equal(disconnected.telemetry.pose.quality, "stale");
  assert.equal(disconnected.telemetry.scan.fresh, false);

  const invalid = adapter.ingestMissionStatus("not-json", 3001);
  assert.match(invalid.telemetry.diagnostics.message, /不是有效 JSON/);
  assert.equal(invalid.mission.state, "idle");
});

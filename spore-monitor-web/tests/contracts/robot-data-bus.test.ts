import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { buildRouteDocument } from "../../lib/route-schema";
import { MissionSimulator, ReplayDataSource, RobotDataBus, type ReplayBundle } from "../../lib/robot-data-bus";

function route() {
  return buildRouteDocument([[0, 0], [40, 0], [40, 20], [0, 20]], {
    scale: 10, reference: [0, 0], rotationTheta: 0, rotationCenter: [0, 0], fieldPolygonMeters: [[0, 0], [4, 0], [4, 2], [0, 2]], ridgeDatabase: {}, evaluationGrid: [], cumulativeConfidence: [], gridStepPx: 1,
    roundNodes: [[{ real_xy: [0, 0], rot_xy: [0, 0], ridge_idx: 0 }, { real_xy: [20, 0], rot_xy: [20, 0], ridge_idx: 0 }, { real_xy: [40, 0], rot_xy: [40, 0], ridge_idx: 0 }]],
    roundTours: [[0, 1, 2]], roundSegments: [[{ from: 0, to: 1, dist_m: 2, time_s: 20, waypoints: [[0, 0], [20, 0]] }, { from: 1, to: 2, dist_m: 2, time_s: 20, waypoints: [[20, 0], [40, 0]] }, { from: 2, to: 0, dist_m: 4, time_s: 40, waypoints: [[40, 0], [0, 0]] }]],
    samplingPoints: [
      { point_id: "R1-P1", real_xy: [0, 0], x_m: 0, y_m: 0, ridge_idx: 0, round: 1, turbidity: null, risk: "pending", read_time: "", pcr_ct: null, pcr_conc: null, pcr_qual: "pending", pcr_gene: null, pcr_verdict: "" },
      { point_id: "R1-P2", real_xy: [20, 0], x_m: 2, y_m: 0, ridge_idx: 0, round: 1, turbidity: null, risk: "pending", read_time: "", pcr_ct: null, pcr_conc: null, pcr_qual: "pending", pcr_gene: null, pcr_verdict: "" },
      { point_id: "R1-P3", real_xy: [40, 0], x_m: 4, y_m: 0, ridge_idx: 0, round: 1, turbidity: null, risk: "pending", read_time: "", pcr_ct: null, pcr_conc: null, pcr_qual: "pending", pcr_gene: null, pcr_verdict: "" },
    ], coveragePct: 80, averageConfidence: .8, totalDistance: 8, totalTime: 80, candidateCount: 3,
  }, [{ point_id: "R1-P1", real_xy: [0, 0], x_m: 0, y_m: 0, ridge_idx: 0, round: 1, turbidity: null, risk: "pending", read_time: "", pcr_ct: null, pcr_conc: null, pcr_qual: "pending", pcr_gene: null, pcr_verdict: "" }, { point_id: "R1-P2", real_xy: [20, 0], x_m: 2, y_m: 0, ridge_idx: 0, round: 1, turbidity: null, risk: "pending", read_time: "", pcr_ct: null, pcr_conc: null, pcr_qual: "pending", pcr_gene: null, pcr_verdict: "" }, { point_id: "R1-P3", real_xy: [40, 0], x_m: 4, y_m: 0, ridge_idx: 0, round: 1, turbidity: null, risk: "pending", read_time: "", pcr_ct: null, pcr_conc: null, pcr_qual: "pending", pcr_gene: null, pcr_verdict: "" }], { refLength: 10, ridgeDistance: 2, samplesPerRound: 3, sporeRadius: 4, rounds: 1, vehicleSpeed: 0.12 }, { fieldId: "field-demo", routeId: "route-demo-001" });
}

test("same route and ticks produce a deterministic mock mission sequence", () => {
  const left = new MissionSimulator(1000, 200), right = new MissionSimulator(1000, 200);
  for (const simulator of [left, right]) { simulator.load(route(), "mission-demo-001"); simulator.start(); for (let i = 0; i < 800; i++) simulator.tick(100); }
  assert.deepEqual(left.snapshot(), right.snapshot());
  assert.equal(left.snapshot().mission.state, "finished");
  assert.ok(left.snapshot().events.some((event) => event.event === "sampling_finished"));
});

test("fault injection never presents a failed or paused run as normal completion", () => {
  const simulator = new MissionSimulator(1000, 200); simulator.load(route()); simulator.start(); simulator.setFault("obstacle_stop", true); simulator.tick(100);
  assert.equal(simulator.snapshot().mission.state, "paused"); assert.equal(simulator.snapshot().telemetry.scan.obstacle_stop, true);
  simulator.setFault("obstacle_stop", false); simulator.resume(); simulator.setFault("sampler_failed", true);
  for (let i = 0; i < 400; i++) simulator.tick(100);
  assert.equal(simulator.snapshot().mission.state, "failed"); assert.equal(simulator.snapshot().mission.fault_code, "SAMPLER_FAILED");
  simulator.setFault("low_battery", true); simulator.setFault("rtk_degraded", true); simulator.setFault("scan_timeout", true);
  const status = simulator.snapshot(); assert.equal(status.telemetry.battery.low, true); assert.equal(status.telemetry.rtk.state, "float"); assert.equal(status.telemetry.scan.fresh, false);
});

test("replay is versioned and selects frames deterministically", () => {
  const fixturePath = join(dirname(fileURLToPath(import.meta.url)), "../fixtures/contracts/replay-normal.json");
  const replay = new ReplayDataSource(); replay.load(JSON.parse(readFileSync(fixturePath, "utf8")) as ReplayBundle);
  assert.equal(replay.snapshot().mission.state, "loaded"); replay.tick(1000); assert.equal(replay.snapshot().mission.state, "sampling");
  const bus = new RobotDataBus(); bus.replay.load(JSON.parse(readFileSync(fixturePath, "utf8")) as ReplayBundle); bus.setMode("replay"); bus.tick(1000); assert.equal(bus.snapshot().mode, "replay");
});

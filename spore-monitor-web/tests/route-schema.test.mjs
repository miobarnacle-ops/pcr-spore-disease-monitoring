import assert from "node:assert/strict";
import test from "node:test";
import { buildRouteDocument, validateRouteDocument } from "../lib/route-schema.ts";

function fixture(overrides = {}) {
  return {
    scale: 10,
    reference: [0, 0],
    rotationTheta: 0,
    roundSegments: [[{ from: 0, to: 1, dist_m: 4, time_s: 40, waypoints: [[10, 20], [50, 20]] }]],
    roundNodes: [[
      { real_xy: [10, 20], rot_xy: [10, 20], ridge_idx: 0 },
      { real_xy: [50, 20], rot_xy: [50, 20], ridge_idx: 0 },
    ]],
    coveragePct: 80,
    averageConfidence: 0.8,
    totalDistance: 4,
    totalTime: 40,
    ...overrides,
  };
}

const polygon = [[0, 0], [100, 0], [100, 60], [0, 60]];
const samples = [
  { point_id: "R1-P1", real_xy: [10, 20], round: 1, ridge_idx: 0 },
  { point_id: "R1-P2", real_xy: [50, 20], round: 1, ridge_idx: 0 },
];

test("exports pixel waypoints as field metres with a sampling identity", () => {
  const route = buildRouteDocument(polygon, fixture(), samples, { vehicleSpeed: 0.5 });
  assert.deepEqual(route.field_polygon_m, [[0, 0], [10, 0], [10, 6], [0, 6]]);
  assert.deepEqual(route.path.map(({ x_m, y_m }) => [x_m, y_m]), [[1, 2], [5, 2]]);
  assert.equal(route.path[0].sample_id, "R1-P1");
  assert.equal(route.path[1].sample_id, "R1-P2");
  assert.equal(route.unit, "m");
});

test("validates a normal route and reports geometry statistics", () => {
  const route = buildRouteDocument(polygon, fixture(), samples, { vehicleSpeed: 0.5 });
  const result = validateRouteDocument(route);
  assert.equal(result.valid, true);
  assert.equal(result.errors.length, 0);
  assert.equal(result.stats.waypoint_count, 2);
  assert.equal(result.stats.sampling_waypoint_count, 2);
  assert.equal(result.stats.path_distance_m, 4);
});

test("rejects a route outside the field or above the vehicle limit", () => {
  const route = buildRouteDocument(
    polygon,
    fixture({ roundSegments: [[{ from: 0, to: 1, dist_m: 80, time_s: 1, waypoints: [[10, 20], [900, 20]] }]] }),
    samples,
    { vehicleSpeed: 1, maxLinearMps: 0.12 },
  );
  route.path[1].speed_limit_mps = 0.5;
  const result = validateRouteDocument(route);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((error) => error.includes("速度")));
  assert.ok(result.errors.some((error) => error.includes("边界外")));
});

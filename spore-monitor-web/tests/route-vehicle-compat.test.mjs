import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { buildRouteDocument, validateRouteDocument } from "../lib/route-schema.ts";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const vehicleRoot = process.env.VEHICLE_NAV_ROOT ?? path.resolve(testDir, "../../spore-vehicle-nav");
const vehiclePackageRoot = path.join(vehicleRoot, "src", "spore_patrol_route_validation");

test("web export is accepted by the vehicle-side route parser", () => {
  const route = buildRouteDocument(
    [[0, 0], [100, 0], [100, 60], [0, 60]],
    {
      scale: 10,
      reference: [0, 0],
      rotationTheta: 0,
      roundSegments: [[{
        from: 0,
        to: 1,
        dist_m: 4,
        time_s: 40,
        waypoints: [[10, 20], [30, 20], [50, 20]],
      }]],
      roundNodes: [[
        { real_xy: [10, 20], rot_xy: [10, 20], ridge_idx: 0 },
        { real_xy: [50, 20], rot_xy: [50, 20], ridge_idx: 0 },
      ]],
      coveragePct: 80,
      averageConfidence: 0.8,
      totalDistance: 4,
      totalTime: 40,
    },
    [
      { point_id: "R1-P1", real_xy: [10, 20], round: 1, ridge_idx: 0 },
      { point_id: "R1-P2", real_xy: [50, 20], round: 1, ridge_idx: 0 },
    ],
    { vehicleSpeed: 0.12 },
    { routeId: "cross-repo-compatibility" },
  );

  assert.equal(validateRouteDocument(route).valid, true);
  assert.equal(route.schema_version, "1.0");
  assert.equal(route.frame_id, "field");
  assert.equal(route.coordinate_type, "local_enu");
  assert.equal(route.unit, "m");
  assert.equal(Object.hasOwn(route.meta, "frame_id"), false);
  assert.equal(Object.hasOwn(route.meta, "coordinate_type"), false);
  assert.equal(Object.hasOwn(route.meta, "unit"), false);
  assert.ok(route.path.every((waypoint) => Object.hasOwn(waypoint, "sample_id")));
  assert.equal(route.path[1].sample_id, null);

  const python = spawnSync(
    process.env.PYTHON ?? "python3",
    ["-c", "import json, sys; from spore_patrol_route_validation.route_model import parse_route; route = parse_route(json.load(sys.stdin)); print(len(route.path))"],
    {
      cwd: vehicleRoot,
      input: JSON.stringify(route),
      encoding: "utf8",
      env: {
        ...process.env,
        PYTHONPATH: [vehiclePackageRoot, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
      },
    },
  );

  assert.equal(python.status, 0, python.error?.message ?? python.stderr);
  assert.equal(python.stdout.trim(), String(route.path.length));
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { ContractValidationError, isFresh, parseMissionStatus, parseRobotTelemetry } from "../../lib/integration-contract";

const fixtures = join(dirname(fileURLToPath(import.meta.url)), "../fixtures/contracts");
const read = (name: string) => JSON.parse(readFileSync(join(fixtures, name), "utf8"));

test("accepts the shared normal mission and telemetry fixtures", () => {
  const mission = parseMissionStatus(read("mission-status-valid.json"));
  const telemetry = parseRobotTelemetry(read("robot-telemetry-valid.json"));
  assert.equal(mission.state, "running");
  assert.equal(mission.sample_id, "R1-P2");
  assert.equal(telemetry.pose.frame_id, "map");
  assert.equal(telemetry.rtk.state, "unavailable");
});

test("rejects unknown states, missing fields and stale payloads deterministically", () => {
  assert.throws(() => parseMissionStatus(read("mission-status-unknown-state.json")), (error: unknown) => error instanceof ContractValidationError && error.code === "UNKNOWN_ENUM");
  const missing = read("mission-status-valid.json"); delete missing.mission_id;
  assert.throws(() => parseMissionStatus(missing), (error: unknown) => error instanceof ContractValidationError && error.code === "INVALID_FIELD");
  assert.equal(isFresh(1000, 1400, 500), true);
  assert.equal(isFresh(1000, 1600, 500), false);
  assert.equal(isFresh(2000, 1600, 500), false);
});

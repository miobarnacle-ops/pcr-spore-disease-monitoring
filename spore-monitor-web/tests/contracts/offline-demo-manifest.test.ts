import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("offline demo manifest covers the mandatory normal and fault scenarios", async () => {
  const manifest = JSON.parse(await readFile(new URL("../fixtures/demo/offline-demo-scenarios.json", import.meta.url), "utf8")) as { schema_version: string; kind: string; scenarios: Array<{ id: string; expected: string }> };
  assert.equal(manifest.schema_version, "1.0");
  assert.equal(manifest.kind, "offline_demo_scenarios");
  const ids = new Set(manifest.scenarios.map((scenario) => scenario.id));
  for (const id of ["normal-replay", "rtk-degraded", "low-battery", "obstacle-stop", "sampler-failed", "disconnect-recovery"]) assert.ok(ids.has(id), `missing ${id}`);
  assert.ok(manifest.scenarios.every((scenario) => scenario.expected.length > 0));
});

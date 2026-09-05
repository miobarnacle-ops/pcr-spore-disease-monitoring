import assert from "node:assert/strict";
import test from "node:test";
import { LOCAL_KEYS, LocalSessionRepository, parseConsoleSession, type StorageLike } from "../../lib/local-session-repository";

class MemoryStorage implements StorageLike {
  values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

test("migrates a legacy v5 session into the versioned v6 envelope", () => {
  const session = parseConsoleSession({ version: 5, polygon: [], samples: [], alerts: [], diseaseRecords: [], environmentHistory: [], fieldRegistry: [], forecastHistory: [] });
  assert.equal(session.schema_version, "6.0");
  assert.equal(session.kind, "inspection_console_session");
  assert.equal(session.payload.version, 5);
});

test("rejects unknown versions and sensitive fields without overwriting the workspace", () => {
  const storage = new MemoryStorage();
  const repository = new LocalSessionRepository(storage);
  repository.saveWorkspace({ polygon: [], samples: [], alerts: [], diseaseRecords: [], environmentHistory: [], fieldRegistry: [], forecastHistory: [], marker: "stable" });
  const previous = storage.getItem(LOCAL_KEYS.workspace);
  assert.throws(() => repository.importSession(JSON.stringify({ schema_version: "7.0", kind: "inspection_console_session", payload: {} })), /不支持的会话版本/);
  assert.equal(storage.getItem(LOCAL_KEYS.workspace), previous);
  assert.throws(() => repository.importSession(JSON.stringify({ version: 5, polygon: [], samples: [], alerts: [], diseaseRecords: [], environmentHistory: [], fieldRegistry: [], forecastHistory: [], password: "do-not-store" })), /凭据/);
  assert.equal(storage.getItem(LOCAL_KEYS.workspace), previous);
});

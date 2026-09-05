/**
 * 浏览器本地仓库：集中管理离线 JSON、会话封装和迁移。
 * 不保存网络凭据；这是本地控制台的持久化边界，而不是云端数据库。
 */

export const LOCAL_KEYS = {
  workspace: "inspection-workspace-v6",
  presets: "inspection-presets-v4",
  history: "inspection-history-v4",
  alerts: "monitoring-alerts-v4",
  envHistory: "environment-history-v4",
  fieldRegistry: "field-registry-v4",
  forecastHistory: "forecast-history-v4",
  diseaseRecords: "disease-evaluation-v4",
} as const;

export type DataOrigin = "user_input" | "simulation" | "replay" | "derived";

export interface ConsoleSession<T extends Record<string, unknown> = Record<string, unknown>> {
  schema_version: "6.0";
  kind: "inspection_console_session";
  exported_at: string;
  origins: Record<string, DataOrigin>;
  payload: T;
}

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function browserStorage(): StorageLike | null {
  return typeof window === "undefined" ? null : window.localStorage;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function assertSafePayload(value: unknown, key = "root"): void {
  if (/password|passwd|token|secret|credential|authorization/i.test(key)) throw new Error("会话不能包含设备凭据或网络密钥。");
  if (Array.isArray(value)) { value.forEach((item, index) => assertSafePayload(item, `${key}[${index}]`)); return; }
  if (isRecord(value)) Object.entries(value).forEach(([childKey, childValue]) => assertSafePayload(childValue, childKey));
}

function validatePayload(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) throw new Error("会话 payload 必须是对象。");
  for (const key of ["polygon", "samples", "diseaseRecords", "environmentHistory", "alerts", "fieldRegistry", "forecastHistory"]) {
    if (key in value && !Array.isArray(value[key])) throw new Error(`会话字段 ${key} 必须是数组。`);
  }
  assertSafePayload(value);
  return value;
}

const DEFAULT_ORIGINS: Record<string, DataOrigin> = {
  polygon: "user_input", planParams: "user_input", planning: "derived", samples: "simulation",
  curve: "user_input", weather: "user_input", forecast: "derived", diseaseRecords: "user_input",
  environmentHistory: "simulation", alerts: "derived", fieldRegistry: "user_input", forecastHistory: "derived",
};

/** 创建当前的 v6 会话；只序列化调用方显式传入的业务数据。 */
export function createConsoleSession<T extends Record<string, unknown>>(payload: T, origins: Record<string, DataOrigin> = {}): ConsoleSession<T> {
  const safe = validatePayload(payload) as T;
  return {
    schema_version: "6.0", kind: "inspection_console_session", exported_at: new Date().toISOString(),
    origins: { ...DEFAULT_ORIGINS, ...origins }, payload: safe,
  };
}

/** 支持此前导出的 version: 5 文件，读取后统一迁移为 v6 内存模型。 */
export function parseConsoleSession(raw: unknown): ConsoleSession {
  if (!isRecord(raw)) throw new Error("会话文件必须是 JSON 对象。");
  if (raw.schema_version === "6.0" && raw.kind === "inspection_console_session") {
    if (!isRecord(raw.origins)) throw new Error("会话 origins 缺失或无效。");
    const origins = Object.fromEntries(Object.entries(raw.origins).filter(([, value]) => value === "user_input" || value === "simulation" || value === "replay" || value === "derived")) as Record<string, DataOrigin>;
    return createConsoleSession(validatePayload(raw.payload), origins);
  }
  if (raw.version === 5) return createConsoleSession(validatePayload(raw));
  throw new Error("不支持的会话版本；仅支持 version 5 或 schema_version 6.0。");
}

export function loadLocalJson<T>(key: string, fallback: T, storage: StorageLike | null = browserStorage()): T {
  if (!storage) return fallback;
  try { const raw = storage.getItem(key); return raw ? JSON.parse(raw) as T : fallback; }
  catch { return fallback; }
}

export function saveLocalJson<T>(key: string, value: T, storage: StorageLike | null = browserStorage()): void {
  if (!storage) return;
  try { storage.setItem(key, JSON.stringify(value)); }
  catch { /* 存储空间不足时保留当前内存状态，并允许用户导出会话。 */ }
}

export class LocalSessionRepository {
  constructor(private readonly storage: StorageLike | null = browserStorage()) {}

  loadWorkspace(): ConsoleSession | null {
    if (!this.storage) return null;
    try {
      const raw = this.storage.getItem(LOCAL_KEYS.workspace);
      return raw ? parseConsoleSession(JSON.parse(raw)) : null;
    } catch { return null; }
  }

  saveWorkspace(payload: Record<string, unknown>, origins?: Record<string, DataOrigin>): ConsoleSession {
    const session = createConsoleSession(payload, origins);
    try { if (this.storage) this.storage.setItem(LOCAL_KEYS.workspace, JSON.stringify(session)); }
    catch { /* 空间不足时，当前内存会话仍可通过显式导出保存。 */ }
    return session;
  }

  importSession(text: string): ConsoleSession {
    const session = parseConsoleSession(JSON.parse(text));
    // 解析、版本和敏感字段检查均通过后才写入，失败不会覆盖当前工作区。
    if (this.storage) this.storage.setItem(LOCAL_KEYS.workspace, JSON.stringify(session));
    return session;
  }
}

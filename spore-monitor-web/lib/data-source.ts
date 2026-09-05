// 数据层抽象：为"模拟数据源"与"真实数据源（机器人/云端）"提供统一接口。
// 当前 DataSource 用 localStorage 提供离线模拟数据（与 V4 控制台行为一致）；
// 后续接入 rosbridge / HTTP API 时，只需实现同一接口的 LiveSource 即可无缝替换。
// 所有方法均返回 Promise，便于未来切换为异步真实源。

import type { EnvironmentSnapshot, MonitoringAlert, FieldRegistryItem, ForecastHistoryRecord } from "./data-types";
import { LOCAL_KEYS, loadLocalJson, saveLocalJson } from "./local-session-repository";

export interface DataSource {
  // 环境快照
  listEnvironmentSnapshots(): Promise<EnvironmentSnapshot[]>;
  appendEnvironmentSnapshot(snapshot: EnvironmentSnapshot): Promise<EnvironmentSnapshot[]>;
  // 告警
  listAlerts(): Promise<MonitoringAlert[]>;
  appendAlert(alert: MonitoringAlert): Promise<MonitoringAlert[]>;
  updateAlert(alert: MonitoringAlert): Promise<MonitoringAlert[]>;
  // 地块
  listFieldRegistry(): Promise<FieldRegistryItem[]>;
  upsertField(item: FieldRegistryItem): Promise<FieldRegistryItem[]>;
  // 预测历史
  listForecastHistory(): Promise<ForecastHistoryRecord[]>;
  appendForecastHistory(record: ForecastHistoryRecord): Promise<ForecastHistoryRecord[]>;
  // 元信息
  readonly sourceName: string;
  readonly isLive: boolean;
}

/** 离线模拟数据源（localStorage 持久化，行为与当前 V4 控制台一致） */
export class LocalDataSource implements DataSource {
  readonly sourceName = "本地模拟数据源 (localStorage)";
  readonly isLive = false;

  async listEnvironmentSnapshots(): Promise<EnvironmentSnapshot[]> {
    return loadLocalJson<EnvironmentSnapshot[]>(LOCAL_KEYS.envHistory, []);
  }
  async appendEnvironmentSnapshot(snapshot: EnvironmentSnapshot): Promise<EnvironmentSnapshot[]> {
    const next = [...(await this.listEnvironmentSnapshots()), snapshot].slice(-500);
    saveLocalJson(LOCAL_KEYS.envHistory, next);
    return next;
  }

  async listAlerts(): Promise<MonitoringAlert[]> {
    return loadLocalJson<MonitoringAlert[]>(LOCAL_KEYS.alerts, []);
  }
  async appendAlert(alert: MonitoringAlert): Promise<MonitoringAlert[]> {
    const next = [alert, ...(await this.listAlerts())].slice(0, 300);
    saveLocalJson(LOCAL_KEYS.alerts, next);
    return next;
  }
  async updateAlert(updated: MonitoringAlert): Promise<MonitoringAlert[]> {
    const next = (await this.listAlerts()).map((alert) => (alert.id === updated.id ? updated : alert));
    saveLocalJson(LOCAL_KEYS.alerts, next);
    return next;
  }

  async listFieldRegistry(): Promise<FieldRegistryItem[]> {
    return loadLocalJson<FieldRegistryItem[]>(LOCAL_KEYS.fieldRegistry, []);
  }
  async upsertField(item: FieldRegistryItem): Promise<FieldRegistryItem[]> {
    const next = [...(await this.listFieldRegistry()).filter((f) => f.name !== item.name), item];
    saveLocalJson(LOCAL_KEYS.fieldRegistry, next);
    return next;
  }

  async listForecastHistory(): Promise<ForecastHistoryRecord[]> {
    return loadLocalJson<ForecastHistoryRecord[]>(LOCAL_KEYS.forecastHistory, []);
  }
  async appendForecastHistory(record: ForecastHistoryRecord): Promise<ForecastHistoryRecord[]> {
    const next = [...(await this.listForecastHistory()), record].slice(-300);
    saveLocalJson(LOCAL_KEYS.forecastHistory, next);
    return next;
  }
}

let instance: DataSource | null = null;
/** 单例访问入口：后续接入真实源时在这里替换实现即可 */
export function getDataSource(): DataSource {
  if (!instance) instance = new LocalDataSource();
  return instance;
}

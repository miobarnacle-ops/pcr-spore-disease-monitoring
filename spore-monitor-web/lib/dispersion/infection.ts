// 侵染窗口耦合：把孢子浓度场翻译成"未来 N 天发病概率"——
// 直接支撑比赛"提前 3-7 天病害预警"硬指标。
// 物理链条：沉降剂量 × 侵染窗口(适温 + 湿度 + 叶面湿润时长) × 潜育期 → 逐格发病概率。
import type { ForecastSlice } from "../inspection-engine";
import type { InfectionRiskField, InfectionWindowParams, WeatherSeries } from "./types";

/** 统计最长连续的"适温 + 湿度达标 + 叶面湿润"时段；无需水膜的病害仍须满足温湿条件。 */
export function infectionWindowSatisfied(series: WeatherSeries, window: InfectionWindowParams): { satisfied: boolean; wetHours: number } {
  let currentWetHours = 0, longestWetHours = 0, favorableHours = 0;
  for (const hourWeather of series) {
    const inTemperature = hourWeather.temperature >= window.tempMin && hourWeather.temperature <= window.tempMax;
    const humidityReached = hourWeather.humidity >= window.rhThreshold;
    const leafWet = hourWeather.leafWetness > 0;
    const favorable = inTemperature && humidityReached;
    if (favorable) favorableHours += 1;
    if (favorable && leafWet) {
      currentWetHours += 1;
      longestWetHours = Math.max(longestWetHours, currentWetHours);
    } else {
      currentWetHours = 0;
    }
  }
  const satisfied = window.dewHoursMin === 0
    ? favorableHours > 0
    : longestWetHours >= window.dewHoursMin;
  return { satisfied, wetHours: longestWetHours };
}

/** 剂量-侵染概率：p = 1 - exp(-dose/k)。k 为剂量尺度（copies/m³），默认使告警阈值 5000 对应约 63% 侵染概率。 */
export function onsetProbability(dose: number, satisfied: boolean, k = 5000): number {
  if (!satisfied || dose <= 0) return 0;
  return 1 - Math.exp(-Math.max(0, dose) / k);
}

/**
 * 某预报期的逐格发病概率场。
 * horizonDays 为剂量来源的预报期（天，与 ForecastSlice 的小时键 days*24 对应）；
 * 显症时间为 horizonDays + latentPeriodDays 天后（UI 负责展示该偏移）。
 */
export function computeInfectionRisk(slice: ForecastSlice, series: WeatherSeries, window: InfectionWindowParams, horizonDays: number): InfectionRiskField {
  if (window.dewHoursMin < 0) throw new Error("侵染窗口参数非法：dewHoursMin 不能为负。");
  const { satisfied, wetHours } = infectionWindowSatisfied(series, window);
  const probabilities = slice.concentrations.map((dose, index) => (slice.inside[index] ? onsetProbability(dose, satisfied) : 0));
  return {
    grid: slice.grid, cols: slice.cols, rows: slice.rows, gridStep: slice.gridStep,
    minX: slice.minX, maxX: slice.maxX, minY: slice.minY, maxY: slice.maxY,
    inside: slice.inside, probabilities,
    horizonDays, diseaseId: window.diseaseId, windowSatisfied: satisfied, wetHours,
  };
}

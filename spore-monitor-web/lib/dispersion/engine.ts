// 扩散预测统一编排入口： assimilation(源项反演) → engine(播种预报) → ab-compare(对照) → infection(预警)。
// UI 只需调用 runDispersionForecast 一个函数。
import { classifyStability, runForecast } from "../inspection-engine";
import type { FusionField, PlanningResult, Point, WeatherParams } from "../inspection-engine";
import { estimateSource, extractObservations } from "./assimilation";
import { compareModels } from "./ab-compare";
import { computeInfectionRisk } from "./infection";
import { INFECTION_WINDOWS } from "./parameters";
import { buildDiurnalWeather } from "./wind";
import type { AbComparisonResult, DispersionForecastBundle, DispersionForecastOptions, InfectionRiskField, SourceEstimate } from "./types";

/**
 * 守卫规则：
 * - 有效 PCR 观测 < 2：跳过源项反演（单观测径向退化），退化为纯融合预报（sourceEstimate=null）；
 * - compare 仅在已有源估计时执行（对照组需要一致的源）；
 * - infection.horizons 以天为单位（3/5/7），与预报小时键 days*24 对齐，缺期自动跳过。
 */
export function runDispersionForecast(
  polygon: Point[],
  planning: PlanningResult,
  baseline: FusionField,
  weather: WeatherParams,
  options: DispersionForecastOptions = {},
): DispersionForecastBundle {
  const observations = options.samples ? extractObservations(options.samples) : [];
  const stability = classifyStability(weather.windSpeed, weather.daytime, weather.cloud);
  let sourceEstimate: SourceEstimate | null = null;
  if (observations.length >= 2) {
    sourceEstimate = estimateSource(
      observations,
      { minX: baseline.minX, maxX: baseline.maxX, minY: baseline.minY, maxY: baseline.maxY },
      weather.windSpeed, weather.windDirection, stability, options.pfConfig,
    );
  }
  const hoursList = options.hoursList ?? [72, 120, 168];
  const forecast = runForecast(polygon, planning, baseline, weather, hoursList, {
    windSeries: options.windSeries,
    fate: options.fate,
    source: sourceEstimate ?? undefined,
  });
  let comparison: AbComparisonResult | null = null;
  if (options.compare && sourceEstimate) {
    comparison = compareModels(sourceEstimate, polygon, planning, baseline, weather, observations, hoursList, options.fate);
  }
  const infectionRisk: Record<number, InfectionRiskField> = {};
  if (options.infection) {
    const window = INFECTION_WINDOWS[options.infection.diseaseId];
    if (!window) throw new Error(`未知病害 ID：${options.infection.diseaseId}（侵染窗口表中不存在）。`);
    for (const days of options.infection.horizons) {
      const slice = forecast[days * 24];
      if (!slice) continue;
      infectionRisk[days] = computeInfectionRisk(slice, buildDiurnalWeather(weather, days * 24), window, days);
    }
  }
  return { forecast, sourceEstimate, infectionRisk, comparison, observations };
}

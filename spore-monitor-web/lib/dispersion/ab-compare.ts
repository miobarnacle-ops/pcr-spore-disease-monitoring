// 高斯烟羽对照场生成 + A/B 模型对比器。
// 复活 inspection-engine.gaussianPlume 作为运行时对照组：
// 同源、同风、同参数下"高斯烟羽 vs 欧拉引擎 vs PCR 实测点"，
// 为比赛要求的"与现有技术差异度≥30%"提供可复现的量化证据。
import { classifyStability, gaussianPlume, runForecast } from "../inspection-engine";
import type { ForecastResult, ForecastSlice, FusionField, PlanningResult, Point, StabilityClass, WeatherParams } from "../inspection-engine";
import type { AbComparisonResult, AbComparisonSlice, GridGeometry, ObservationPoint, SourceEstimate, SporeFateParams } from "./types";

/** 在融合网格几何上逐格求值稳态高斯烟羽，输出与 ForecastResult 同构的对照场（各期相同：烟羽为稳态解）。 */
export function buildPlumeField(source: SourceEstimate, geometry: GridGeometry, wind: number, direction: number, stability: StabilityClass, horizons: number[] = [72, 120, 168]): ForecastResult {
  const concentrations = geometry.grid.map(([x, y]) => Math.max(0, gaussianPlume(source.x, source.y, source.strength, wind, direction, stability, x, y)));
  const insideValues = concentrations.filter((_, index) => geometry.inside[index]).sort((a, b) => a - b);
  const peak = insideValues[insideValues.length - 1] ?? 0;
  const p90 = insideValues[Math.floor(Math.max(0, insideValues.length - 1) * .9)] ?? 0;
  const mean = insideValues.length ? insideValues.reduce((sum, value) => sum + value, 0) / insideValues.length : 0;
  const slice: ForecastSlice = {
    grid: geometry.grid, concentrations, inside: geometry.inside,
    minX: geometry.minX, maxX: geometry.maxX, minY: geometry.minY, maxY: geometry.maxY,
    gridStep: geometry.gridStep, cols: geometry.cols, rows: geometry.rows,
    stability, peak, p90, mean, model: "gaussian-plume",
  };
  const result: ForecastResult = {};
  for (const horizon of horizons) result[horizon] = slice;
  return result;
}

function sampleGrid(slice: ForecastSlice, x: number, y: number): number {
  const col = Math.min(slice.cols - 1, Math.max(0, Math.round((x - slice.minX) / slice.gridStep)));
  const row = Math.min(slice.rows - 1, Math.max(0, Math.round((y - slice.minY) / slice.gridStep)));
  return slice.concentrations[col * slice.rows + row];
}

const LOG_FLOOR = 1;

function metrics(modelValues: number[], observations: ObservationPoint[]) {
  let squareSum = 0, sum = 0;
  for (let index = 0; index < observations.length; index++) {
    const residual = Math.log10(Math.max(LOG_FLOOR, modelValues[index])) - Math.log10(Math.max(LOG_FLOOR, observations[index].concentration));
    squareSum += residual ** 2;
    sum += residual;
  }
  const count = Math.max(1, observations.length);
  return { rmse: Math.sqrt(squareSum / count), bias: sum / count };
}

/**
 * 同条件 A/B 对比：欧拉引擎（含源播种）与解析烟羽在各预报期于 PCR 观测点处的
 * log10 RMSE / 偏差。两组指标使用同一组观测，可直接进报告表格。
 */
export function compareModels(
  source: SourceEstimate,
  polygon: Point[],
  planning: PlanningResult,
  baseline: FusionField,
  weather: WeatherParams,
  observations: ObservationPoint[],
  horizons: number[] = [72, 120, 168],
  fate?: SporeFateParams,
): AbComparisonResult {
  if (!observations.length) throw new Error("A/B 对比需要至少 1 个 PCR 观测点。");
  const stability = classifyStability(weather.windSpeed, weather.daytime, weather.cloud);
  const euler = runForecast(polygon, planning, baseline, weather, horizons, { source, fate });
  const plumeField = buildPlumeField(source, baseline, weather.windSpeed, weather.windDirection, stability, horizons);
  const plumeValues = observations.map((obs) => gaussianPlume(source.x, source.y, source.strength, weather.windSpeed, weather.windDirection, stability, obs.x, obs.y));
  const slices: AbComparisonSlice[] = horizons.map((horizon) => {
    const eulerSlice = euler[horizon];
    const eulerValues = eulerSlice ? observations.map((obs) => sampleGrid(eulerSlice, obs.x, obs.y)) : observations.map(() => 0);
    const eulerMetrics = metrics(eulerValues, observations);
    const plumeMetrics = metrics(plumeValues, observations);
    return {
      horizonHours: horizon,
      obsCount: observations.length,
      eulerRMSE: eulerMetrics.rmse,
      eulerBias: eulerMetrics.bias,
      plumeRMSE: plumeMetrics.rmse,
      plumeBias: plumeMetrics.bias,
    };
  });
  return { source, plumeField, slices };
}

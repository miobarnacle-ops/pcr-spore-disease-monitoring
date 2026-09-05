// 冻结的旧版 runForecast（重构前实现，逐字保留）。
// 用途：回归基准 —— 测试中与新引擎在相同输入下实时对比，
// 证明"不传 options 时新引擎与旧版数值等价（容差 1e-9 相对误差）"。
// 此文件是有意保留的重复实现，除类型标注外禁止任何改动。
import { classifyStability, STABILITY } from "../../lib/inspection-engine";
import type { FusionField, PlanningResult, Point, WeatherParams } from "../../lib/inspection-engine";
import type { ForecastResult } from "../../lib/inspection-engine";

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function legacyRunForecast(polygon: Point[], planning: PlanningResult, baseline: FusionField, weather: WeatherParams, hoursList: number[] = [72, 120, 168]): ForecastResult {
  if (polygon.length < 3 || planning.fieldPolygonMeters.length < 3 || !baseline.grid.length) throw new Error("需要闭合边界和已生成的粗精融合基准场。");
  if (weather.diseaseIndex < 0 || weather.diseaseIndex > 100 || weather.lai < 0.5 || weather.lai > 10 || weather.plantHeight < 0.1 || weather.plantHeight > 5) throw new Error("作物表型参数超出范围。DI:0-100, LAI:0.5-10, 株高:0.1-5m。");
  const horizons = [...new Set(hoursList.map((hours) => Math.max(1, Math.round(hours))))].sort((a, b) => a - b);
  const maxHours = horizons[horizons.length - 1] ?? 72;
  const { cols, rows, gridStep, minX, maxX, minY, maxY } = baseline;
  const indexOf = (col: number, row: number) => col * rows + row;
  let state = Float64Array.from(baseline.concentrations);
  const result: ForecastResult = {}, stability = classifyStability(weather.windSpeed, weather.daytime, weather.cloud);
  const stabilityDiffusion: Record<keyof typeof STABILITY, number> = { A: .31, B: .27, C: .23, D: .19, E: .15, F: .12 };
  const effectiveTemperature = .78 * weather.temperature + .22 * (weather.soilTemperature ?? weather.temperature);
  const temperatureSuitability = Math.exp(-((effectiveTemperature - 24) ** 2) / 72);
  const leafWetness = clamp((weather.leafWetness ?? weather.humidity) / 100, 0, 1);
  const soilMoisture = clamp((weather.soilMoisture ?? 55) / 100, 0, 1);
  const humiditySuitability = clamp(.58 * ((weather.humidity - 42) / 48) + .3 * leafWetness + .12 * soilMoisture, 0, 1);
  const ultravioletStress = clamp((weather.lightIntensity ?? 30000) / 90000, 0, 1);
  const rainWashout = clamp((weather.rainfall ?? 0) / 35, 0, .75);
  const diseasePressure = clamp(weather.diseaseIndex / 100, 0, 1);
  const canopyAttenuation = Math.exp(-.38 * weather.lai);
  const canopyCapture = 1 - Math.exp(-.3 * weather.lai);

  const sampleField = (field: Float64Array, x: number, y: number) => {
    const gx = clamp((x - minX) / gridStep, 0, cols - 1), gy = clamp((y - minY) / gridStep, 0, rows - 1);
    const c0 = Math.floor(gx), r0 = Math.floor(gy), c1 = Math.min(cols - 1, c0 + 1), r1 = Math.min(rows - 1, r0 + 1);
    const tx = gx - c0, ty = gy - r0;
    const top = field[indexOf(c0, r0)] * (1 - tx) + field[indexOf(c1, r0)] * tx;
    const bottom = field[indexOf(c0, r1)] * (1 - tx) + field[indexOf(c1, r1)] * tx;
    return top * (1 - ty) + bottom * ty;
  };

  for (let hour = 1; hour <= maxHours; hour++) {
    const direction = (weather.windDirection + 13 * Math.sin(2 * Math.PI * hour / 24) + 5 * Math.sin(2 * Math.PI * hour / 8) + 360) % 360;
    const radians = direction * Math.PI / 180, windX = Math.sin(radians), windY = -Math.cos(radians);
    const nearCanopyWind = Math.max(.08, weather.windSpeed * canopyAttenuation * (.7 + .3 * weather.plantHeight));
    const displacement = Math.min(gridStep * 1.45, nearCanopyWind * 3600 * .0025);
    const diffusion = clamp(stabilityDiffusion[stability] + Math.min(.09, weather.windSpeed * .015), .1, .38);
    const hourlyGrowth = Math.exp(.002 + .012 * temperatureSuitability * humiditySuitability * (.3 + .7 * diseasePressure));
    const hourlyLoss = .006 + .004 * Math.min(weather.windSpeed, 8) + .006 * (1 - humiditySuitability) + .004 * canopyCapture + .007 * ultravioletStress + .018 * rainWashout;
    const survival = Math.exp(-hourlyLoss);
    const reEmission = .01 + .025 * diseasePressure * temperatureSuitability * (.45 + .55 * humiditySuitability) + .006 * rainWashout * leafWetness;
    const next = new Float64Array(state.length);
    for (let col = 0; col < cols; col++) for (let row = 0; row < rows; row++) {
      const index = indexOf(col, row), [x, y] = baseline.grid[index];
      const advected = sampleField(state, x - windX * displacement, y - windY * displacement);
      let neighborSum = 0, neighborWeight = 0;
      for (let dc = -1; dc <= 1; dc++) for (let dr = -1; dr <= 1; dr++) {
        if (!dc && !dr) continue;
        const nc = col + dc, nr = row + dr; if (nc < 0 || nc >= cols || nr < 0 || nr >= rows) continue;
        const weight = dc && dr ? .7 : 1; neighborSum += state[indexOf(nc, nr)] * weight; neighborWeight += weight;
      }
      const diffused = neighborWeight ? neighborSum / neighborWeight : advected;
      const transported = advected * (1 - diffusion) + diffused * diffusion;
      const localSource = baseline.concentrations[index] * reEmission * (.65 + .35 * baseline.reliabilities[index]);
      next[index] = clamp(transported * survival * hourlyGrowth + localSource, 0, 1e8);
    }
    state = next;
    if (horizons.includes(hour)) {
      const concentrations = Array.from(state);
      const fieldValues = concentrations.filter((_, index) => baseline.inside[index]).sort((a, b) => a - b);
      const peak = fieldValues[fieldValues.length - 1] ?? 0, p90 = fieldValues[Math.floor(Math.max(0, fieldValues.length - 1) * .9)] ?? 0;
      const mean = fieldValues.length ? fieldValues.reduce((sum, value) => sum + value, 0) / fieldValues.length : 0;
      result[hour] = { grid: baseline.grid, concentrations, inside: baseline.inside, minX, maxX, minY, maxY, gridStep, cols, rows, stability, peak, p90, mean, model: "fusion-advection-diffusion" };
    }
  }
  return result;
}

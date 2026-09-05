// 回归锁：新引擎不传 options 时必须与冻结的旧版实现数值等价。
// 唯一已知偏差：rainWashout 由 `/35` 参数化为 `* (1/35)`（1-ulp 级浮点差），
// 因此使用 1e-9 相对误差容差而非逐位比较；任何 ≥1e-6 级的行为改变都会被此测试捕获。
import assert from "node:assert/strict";
import { test } from "node:test";
import { buildFusionField, runForecast } from "../../lib/inspection-engine";
import { legacyRunForecast } from "./legacy-reference";
import { FIELD_POLYGON, makePlanning, makeSamples, makeWeather } from "./fixtures";

function maxRelativeError(a: Record<number, { concentrations: number[]; peak: number; p90: number; mean: number }>, b: Record<number, { concentrations: number[]; peak: number; p90: number; mean: number }>): number {
  let worst = 0;
  for (const hour of Object.keys(a)) {
    const h = Number(hour);
    const left = a[h], right = b[h];
    assert.ok(right, `missing horizon ${h}`);
    for (let index = 0; index < left.concentrations.length; index++) {
      const magnitude = Math.max(Math.abs(left.concentrations[index]), Math.abs(right.concentrations[index]), 1e-30);
      worst = Math.max(worst, Math.abs(left.concentrations[index] - right.concentrations[index]) / magnitude);
    }
    for (const key of ["peak", "p90", "mean"] as const) {
      const magnitude = Math.max(Math.abs(left[key]), Math.abs(right[key]), 1e-30);
      worst = Math.max(worst, Math.abs(left[key] - right[key]) / magnitude);
    }
  }
  return worst;
}

test("runForecast without options matches legacy implementation within 1e-9", () => {
  const polygon = FIELD_POLYGON;
  const planning = makePlanning();
  const baseline = buildFusionField(polygon, planning, makeSamples(), 50, 80);
  const weather = makeWeather();
  const legacy = legacyRunForecast(polygon, planning, baseline, weather, [72, 120, 168]);
  const current = runForecast(polygon, planning, baseline, weather, [72, 120, 168]);
  assert.deepEqual(Object.keys(current).sort(), Object.keys(legacy).sort());
  const error = maxRelativeError(legacy, current);
  assert.ok(error <= 1e-9, `regression drift ${error} exceeds 1e-9`);
});

test("runForecast without options matches legacy under night/stability-F weather", () => {
  const polygon = FIELD_POLYGON;
  const planning = makePlanning();
  const baseline = buildFusionField(polygon, planning, makeSamples(), 50, 80);
  const weather = makeWeather({ daytime: false, cloud: 20, windSpeed: 2.2, rainfall: 0 });
  const legacy = legacyRunForecast(polygon, planning, baseline, weather, [24, 72]);
  const current = runForecast(polygon, planning, baseline, weather, [24, 72]);
  const error = maxRelativeError(legacy, current);
  assert.ok(error <= 1e-9, `regression drift ${error} exceeds 1e-9`);
});

test("windSeries suppresses the synthetic wobble (direction = series value)", async () => {
  const { resolveWindDirection, syntheticDirection } = await import("../../lib/dispersion/wind");
  const series = [{ hour: 0, speed: 4, direction: 90 }, { hour: 200, speed: 4, direction: 90 }];
  assert.equal(resolveWindDirection(135, 12, series), 90);
  assert.equal(resolveWindDirection(135, 12), syntheticDirection(135, 12));
});

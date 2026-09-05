// 扩散引擎模块测试：粒子滤波源回收、侵染窗口、A/B 对比、编排守卫、参数表引用。
import assert from "node:assert/strict";
import { test } from "node:test";
import { gaussianPlume } from "../../lib/inspection-engine";
import { buildFusionField, runForecast } from "../../lib/inspection-engine";
import { DEFAULT_SPORE_FATE, INFECTION_WINDOWS, computeFateRates } from "../../lib/dispersion/parameters";
import { estimateSource, extractObservations } from "../../lib/dispersion/assimilation";
import { buildPlumeField, compareModels } from "../../lib/dispersion/ab-compare";
import { computeInfectionRisk, infectionWindowSatisfied, onsetProbability } from "../../lib/dispersion/infection";
import { buildDiurnalWeather } from "../../lib/dispersion/wind";
import { runDispersionForecast } from "../../lib/dispersion/engine";
import { FIELD_POLYGON, makePlanning, makeSamples, makeWeather } from "./fixtures";

const WIND_DEG = 135;
const WIND_UNIT = { x: Math.sin(WIND_DEG * Math.PI / 180), y: -Math.cos(WIND_DEG * Math.PI / 180) };

/** 观测几何：源的下风向锥 3 点（不同距离/横风偏移）+ 上风向 2 点（浓度截断为下限，模拟无信息对照）。 */
function observationsAround(truthX: number, truthY: number, truthQ: number) {
  const normal = { x: -WIND_UNIT.y, y: WIND_UNIT.x };
  const layout = [
    { d: 12, c: -8 },
    { d: 22, c: 5 },
    { d: 34, c: -3 },
    { d: -15, c: 6 },
    { d: -26, c: -5 },
  ];
  return layout.map(({ d, c }) => {
    const x = Math.min(80, Math.max(0, truthX + WIND_UNIT.x * d + normal.x * c));
    const y = Math.min(50, Math.max(0, truthY + WIND_UNIT.y * d + normal.y * c));
    return { x, y, quality: 1, concentration: Math.max(1, gaussianPlume(truthX, truthY, truthQ, 3.5, WIND_DEG, "C", x, y)) };
  });
}

test("particle filter recovers synthetic sources across 50 seeded trials (>=90%)", () => {
  const bounds = { minX: 0, maxX: 80, minY: 0, maxY: 50 };
  let recovered = 0;
  const trials = 50;
  for (let seed = 0; seed < trials; seed++) {
    const truthX = 15 + ((seed * 37) % 50);
    const truthY = 8 + ((seed * 23) % 34);
    const logQ = 4.2 + ((seed % 5) - 2) * 0.4;
    const truthQ = 10 ** logQ;
    const observations = observationsAround(truthX, truthY, truthQ);
    const estimate = estimateSource(observations, bounds, 3.5, WIND_DEG, "C", { seed: seed + 1, particleCount: 2000 });
    const positionHit = Math.abs(estimate.x - truthX) <= 20 && Math.abs(estimate.y - truthY) <= 20;
    const strengthHit = Math.abs(Math.log10(estimate.strength / truthQ)) <= 0.5;
    if (positionHit && strengthHit) recovered += 1;
  }
  assert.ok(recovered / trials >= 0.9, `recovery rate ${(recovered / trials).toFixed(2)} (${recovered}/${trials}) below 90%`);
});

test("particle filter rejects single observation (radial degeneracy) and estimateSource throws", () => {
  const observations = [{ x: 40, y: 25, concentration: 1000, quality: 1 }];
  assert.throws(() => estimateSource(observations, { minX: 0, maxX: 80, minY: 0, maxY: 50 }, 3.5, 135, "C"), /至少 2 个/);
});

test("extractObservations keeps valid/doubtful with concentration, drops pending/invalid/null", () => {
  const observations = extractObservations(makeSamples());
  assert.equal(observations.length, 4);
  assert.ok(observations.every((obs) => obs.concentration > 0));
});

test("infection window: stripe rust satisfied on wet-cool series, rejected on dry series", () => {
  const window = INFECTION_WINDOWS.wheat_stripe_rust;
  const wetSeries = Array.from({ length: 24 }, (_, hour) => ({ hour, temperature: 12, humidity: 92, leafWetness: 1 }));
  const drySeries = Array.from({ length: 24 }, (_, hour) => ({ hour, temperature: 12, humidity: 60, leafWetness: 0 }));
  const wet = infectionWindowSatisfied(wetSeries, window);
  const dry = infectionWindowSatisfied(drySeries, window);
  assert.equal(wet.satisfied, true);
  assert.equal(wet.wetHours, 24);
  assert.equal(dry.satisfied, false);
});

test("onset probability monotonic in dose, zero when window unsatisfied", () => {
  assert.equal(onsetProbability(10000, false), 0);
  assert.equal(onsetProbability(0, true), 0);
  const low = onsetProbability(500, true);
  const mid = onsetProbability(5000, true);
  const high = onsetProbability(50000, true);
  assert.ok(low < mid && mid < high && high < 1);
});

test("computeInfectionRisk gates outside-polygon cells to zero and keeps grid geometry", () => {
  const window = INFECTION_WINDOWS.wheat_stripe_rust;
  const planning = makePlanning();
  const baseline = buildFusionField(FIELD_POLYGON, planning, makeSamples(), 50, 80);
  const forecast = runForecast(FIELD_POLYGON, planning, baseline, makeWeather(), [72], { source: { x: 55, y: 30, strength: 5e5, logStrengthMean: 5.7, logStrengthStd: 0.4, sigmaX: 6, sigmaY: 6, confidence: "medium", obsCount: 4 } });
  const slice = forecast[72];
  const series = buildDiurnalWeather(makeWeather(), 72);
  const risk = computeInfectionRisk(slice, series, window, 3);
  assert.equal(risk.probabilities.length, slice.concentrations.length);
  assert.equal(risk.diseaseId, "wheat_stripe_rust");
  risk.probabilities.forEach((probability, index) => {
    if (!slice.inside[index]) assert.equal(probability, 0);
  });
});

test("buildPlumeField decays monotonically downwind and is deterministic", () => {
  const source = { x: 20, y: 25, strength: 5e5, logStrengthMean: 5.7, logStrengthStd: 0.4, sigmaX: 6, sigmaY: 6, confidence: "medium" as const, obsCount: 4 };
  const planning = makePlanning();
  const baseline = buildFusionField(FIELD_POLYGON, planning, makeSamples(), 50, 80);
  const field = buildPlumeField(source, baseline, 3.5, 0, "D", [72]);
  const slice = field[72];
  // 烟羽中轴线是单峰曲线：受体高度(0.825m)低于排放高度(1.5m)，近场随羽流增长而上升，
  // 越过峰值后按 1/(σy·σz) 与沉降衰减单调下降 —— 断言"单峰 + 峰后单调"而非全程单调。
  const centerline: number[] = [];
  for (let d = 1; d <= 60; d += 2) centerline.push(gaussianPlume(source.x, source.y, source.strength, 3.5, 0, "D", source.x, source.y - d));
  const peakIndex = centerline.indexOf(Math.max(...centerline));
  for (let index = peakIndex + 1; index < centerline.length; index++) {
    assert.ok(centerline[index] <= centerline[index - 1] + 1e-9, `non-monotonic decay after peak at d=${index * 2 + 1}`);
  }
  assert.ok(peakIndex > 0, "peak should not be at the first step");
  assert.ok(centerline[centerline.length - 1] < centerline[peakIndex], "far field must decay below peak");
  // 网格场与解析值一致（最近格点）且确定性可复现
  const row = Math.min(slice.rows - 1, Math.max(0, Math.round((source.y - 20 - slice.minY) / slice.gridStep)));
  const col = Math.min(slice.cols - 1, Math.max(0, Math.round((source.x - slice.minX) / slice.gridStep)));
  const analytic = gaussianPlume(source.x, source.y, source.strength, 3.5, 0, "D", slice.grid[col * slice.rows + row][0], slice.grid[col * slice.rows + row][1]);
  assert.ok(Math.abs(slice.concentrations[col * slice.rows + row] - analytic) <= 1e-9 * Math.max(1, analytic));
  const again = buildPlumeField(source, baseline, 3.5, 0, "D", [72]);
  assert.deepEqual(again[72].concentrations, slice.concentrations);
});

test("compareModels reports aligned metrics for both models and is deterministic", () => {
  const planning = makePlanning();
  const baseline = buildFusionField(FIELD_POLYGON, planning, makeSamples(), 50, 80);
  const observations = extractObservations(makeSamples());
  const source = estimateSource(observations, { minX: baseline.minX, maxX: baseline.maxX, minY: baseline.minY, maxY: baseline.maxY }, 3.5, 135, "C", { seed: 7 });
  const weather = makeWeather();
  const first = compareModels(source, FIELD_POLYGON, planning, baseline, weather, observations, [72, 120, 168]);
  const second = compareModels(source, FIELD_POLYGON, planning, baseline, weather, observations, [72, 120, 168]);
  assert.deepEqual(first.slices, second.slices);
  assert.equal(first.plumeField[72].model, "gaussian-plume");
  first.slices.forEach((slice) => {
    assert.equal(slice.obsCount, observations.length);
    assert.ok(slice.eulerRMSE >= 0 && slice.plumeRMSE >= 0);
  });
});

test("orchestrator: single valid observation degrades to plain fusion forecast (null source)", () => {
  const planning = makePlanning();
  const baseline = buildFusionField(FIELD_POLYGON, planning, [makeSamples()[0]], 50, 80);
  const weather = makeWeather();
  const bundle = runDispersionForecast(FIELD_POLYGON, planning, baseline, weather, { samples: [makeSamples()[0]], hoursList: [72] });
  assert.equal(bundle.sourceEstimate, null);
  assert.equal(bundle.observations.length, 1);
  const plain = runForecast(FIELD_POLYGON, planning, baseline, weather, [72]);
  assert.deepEqual(bundle.forecast[72].concentrations, plain[72].concentrations);
});

test("orchestrator: >=2 observations produce source estimate, seeded forecast differs from plain", () => {
  const planning = makePlanning();
  const baseline = buildFusionField(FIELD_POLYGON, planning, makeSamples(), 50, 80);
  const weather = makeWeather();
  const bundle = runDispersionForecast(FIELD_POLYGON, planning, baseline, weather, {
    samples: makeSamples(),
    hoursList: [72],
    compare: true,
    infection: { diseaseId: "wheat_stripe_rust", horizons: [3] },
  });
  assert.ok(bundle.sourceEstimate);
  assert.equal(bundle.observations.length, 4);
  assert.ok(bundle.comparison);
  assert.deepEqual(Object.keys(bundle.infectionRisk), ["3"]);
  const plain = runForecast(FIELD_POLYGON, planning, baseline, weather, [72]);
  assert.notDeepEqual(bundle.forecast[72].concentrations, plain[72].concentrations);
});

test("orchestrator: unknown disease id rejected", () => {
  const planning = makePlanning();
  const baseline = buildFusionField(FIELD_POLYGON, planning, makeSamples(), 50, 80);
  assert.throws(
    () => runDispersionForecast(FIELD_POLYGON, planning, baseline, makeWeather(), { samples: makeSamples(), infection: { diseaseId: "nope", horizons: [3] } }),
    /未知病害/,
  );
});

test("parameter tables carry verifiable citations", () => {
  assert.ok(DEFAULT_SPORE_FATE.citation.year >= 1900 && DEFAULT_SPORE_FATE.citation.title.length > 0 && DEFAULT_SPORE_FATE.citation.source.length > 0);
  for (const [diseaseId, window] of Object.entries(INFECTION_WINDOWS)) {
    assert.ok(window.citation.year >= 1900, `${diseaseId} citation year missing`);
    assert.ok(window.citation.title.length > 0 && window.citation.source.length > 0, `${diseaseId} citation incomplete`);
    assert.ok(window.tempMin < window.tempOpt && window.tempOpt < window.tempMax, `${diseaseId} temperature window inverted`);
  }
});

test("computeFateRates with defaults reproduces legacy hand-tuned rates", () => {
  const weather = makeWeather();
  const rates = computeFateRates(weather);
  const leafWetness = Math.min(1, Math.max(0, weather.leafWetness / 100));
  const soilMoisture = Math.min(1, Math.max(0, weather.soilMoisture / 100));
  const humiditySuitability = Math.min(1, Math.max(0, .58 * ((weather.humidity - 42) / 48) + .3 * leafWetness + .12 * soilMoisture));
  const rainWashout = Math.min(.75, Math.max(0, weather.rainfall / 35));
  const legacyHourlyLoss = .006 + .004 * Math.min(weather.windSpeed, 8) + .006 * (1 - humiditySuitability) + .004 * (1 - Math.exp(-.3 * weather.lai)) + .007 * Math.min(1, Math.max(0, weather.lightIntensity / 90000)) + .018 * rainWashout;
  assert.ok(Math.abs(rates.hourlyLoss - legacyHourlyLoss) / legacyHourlyLoss < 1e-9, `hourlyLoss drift ${rates.hourlyLoss - legacyHourlyLoss}`);
  assert.ok(rates.survival > 0 && rates.hourlyGrowth > 1 && rates.reEmission > 0);
});

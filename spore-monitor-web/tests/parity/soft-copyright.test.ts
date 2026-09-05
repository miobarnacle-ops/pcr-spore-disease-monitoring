import assert from "node:assert/strict";
import { test } from "node:test";
import fixture from "../fixtures/soft-copyright/v4-core-compatibility.json";
import {
  classifyRisk,
  classifyStability,
  buildFusionField,
  ctToConcentration,
  detectCtOutliers,
  gaussianPlume,
  hasSelfIntersectingBoundary,
  pcrVerdict,
  pearsonComparison,
  pointInPolygon,
  polygonArea,
  polygonCentroid,
  rotatePoint,
  scanlineIntersections,
  solvePlanning,
  runForecast,
  type PcrQuality,
  type SamplingPoint,
} from "../../lib/inspection-engine";

const EPSILON = 1e-10;

function close(actual: number, expected: number, label: string) {
  assert.ok(Math.abs(actual - expected) <= EPSILON, `${label}: ${actual} !== ${expected}`);
}

test("soft-copyright geometry cases retain the declared Web-compatible behavior", () => {
  const polygon = fixture.geometry.polygon as [number, number][];
  const { rotate } = fixture.geometry;
  const actualRotation = rotatePoint(rotate.point as [number, number], rotate.center as [number, number], rotate.thetaRadians);
  close(actualRotation[0], rotate.expected[0], "rotated x");
  close(actualRotation[1], rotate.expected[1], "rotated y");
  assert.equal(pointInPolygon(fixture.geometry.inside.point as [number, number], polygon), fixture.geometry.inside.expected);
  assert.equal(pointInPolygon(fixture.geometry.outside.point as [number, number], polygon), fixture.geometry.outside.expected);
  assert.deepEqual(scanlineIntersections(fixture.geometry.scanline.y, polygon), fixture.geometry.scanline.expected);
  close(polygonArea(polygon), fixture.geometry.area, "polygon area");
});

test("Web corrects the legacy orientation-sign centroid defect instead of reproducing it", () => {
  const centroid = polygonCentroid(fixture.geometry.polygon as [number, number][]);
  close(centroid[0], fixture.geometry.webCorrectedCentroid[0], "corrected centroid x");
  close(centroid[1], fixture.geometry.webCorrectedCentroid[1], "corrected centroid y");
  assert.notDeepEqual(centroid, fixture.geometry.legacyCentroid);
});

test("risk and stability thresholds retain soft-copyright boundary semantics", () => {
  for (const row of fixture.riskCases) assert.equal(classifyRisk(row.value, row.medium, row.high), row.expected);
  for (const row of fixture.stabilityCases) assert.equal(classifyStability(row.wind, row.daytime, row.cloud), row.expected);
});

test("PCR conversion and verdict thresholds retain the declared compatibility cases", () => {
  const curve = fixture.pcr.curve;
  for (const row of fixture.pcr.cases) {
    const quality = row.quality as PcrQuality;
    assert.equal(ctToConcentration(row.ct, quality, row.dilution, curve), row.concentration);
    assert.equal(pcrVerdict(row.ct, quality, curve), row.verdict);
  }
});

test("PCR Ct outlier rule is shared by the engine and keeps the soft-copyright Z-score threshold", () => {
  const points: SamplingPoint[] = [20, 20, 20, 20, 20, 20, 20, 45].map((ct, index) => ({
    point_id: `Z${index + 1}`, real_xy: [index, 0], x_m: index, y_m: 0, ridge_idx: 0, round: 1,
    turbidity: null, risk: "pending", read_time: "", pcr_ct: ct, pcr_conc: 100, pcr_qual: "valid",
    pcr_gene: "ITS1-F/ITS4-R", pcr_verdict: "阳性",
  }));
  points.push({ ...points[0], point_id: "ignored", pcr_ct: 50, pcr_qual: "doubtful" });
  const result = detectCtOutliers(points);
  assert.equal(result.eligibleCount, 8);
  assert.deepEqual(result.flaggedIndices, [7]);
  assert.ok((result.standardDeviation ?? 0) > 0 && (result.mean ?? 0) > 20);
  assert.equal(detectCtOutliers(points.slice(0, 4)).mean, null, "insufficient results must not produce a Z-score verdict");
});

test("planning and comparison retain the inherited workflow semantics without freezing implementation details", () => {
  const polygon: [number, number][] = [[0, 0], [100, 0], [100, 60], [0, 60]];
  const planning = solvePlanning(polygon, { refLength: 10, ridgeDistance: 2, samplesPerRound: 3, sporeRadius: 4, rounds: 1, vehicleSpeed: 0.2 });
  assert.ok(planning.candidateCount > 0 && planning.samplingPoints.length > 0, "planner must generate candidates and sampling points");
  assert.ok(planning.samplingPoints.length <= 3, "planner must not exceed the requested sampling count");
  assert.ok(planning.samplingPoints.every((point) => pointInPolygon(point.real_xy, polygon)), "sampling points must stay inside the field");
  assert.ok(planning.roundSegments[0].length === planning.samplingPoints.length, "each selected point must remain on the closed tour");
  assert.ok(planning.totalDistance > 0 && planning.totalTime > 0, "planning summary must remain usable by the console");

  const comparisonSamples: SamplingPoint[] = fixture.comparison.samples.map((row, index) => ({
    point_id: `C${index + 1}`, real_xy: [index, 0], x_m: index, y_m: 0, ridge_idx: 0, round: 1,
    turbidity: row.turbidity, risk: "pending", read_time: "", pcr_ct: 30, pcr_conc: row.concentration,
    pcr_qual: "valid", pcr_gene: "ITS1-F/ITS4-R", pcr_verdict: row.verdict,
  }));
  const comparison = pearsonComparison(comparisonSamples, fixture.comparison.mediumThreshold, fixture.comparison.highThreshold);
  assert.equal(comparison.count, fixture.comparison.expected.count);
  close(comparison.r, fixture.comparison.expected.r, "Pearson r");
  assert.equal(comparison.agreement, fixture.comparison.expected.agreement);
  close(comparison.agreementPct, fixture.comparison.expected.agreementPct, "agreement percentage");
});

test("planner rejects invalid boundaries and parameters before they can reach route integration", () => {
  const params = { refLength: 10, ridgeDistance: 2, samplesPerRound: 3, sporeRadius: 4, rounds: 1, vehicleSpeed: 0.2 };
  const selfIntersecting: [number, number][] = [[0, 0], [100, 100], [0, 100], [100, 0]];
  assert.equal(hasSelfIntersectingBoundary(selfIntersecting), true);
  assert.throws(() => solvePlanning([[0, 0], [100, 0]], params), /闭合农田边界/);
  assert.throws(() => solvePlanning([[0, 0], [0, 0], [100, 60], [0, 60]], params), /重复顶点/);
  assert.throws(() => solvePlanning(selfIntersecting, params), /不能自相交/);
  assert.throws(() => solvePlanning([[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]], params), /基准边像素长度过短/);
  assert.throws(() => solvePlanning([[0, 0], [100, 0], [Number.NaN, 60], [0, 60]], params), /有限数值/);
  assert.throws(() => solvePlanning([[0, 0], [100, 0], [100, 60], [0, 60]], { ...params, sporeRadius: 0 }), /必须为正数/);
  assert.equal(detectCtOutliers([]).eligibleCount, 0, "empty PCR data must not produce an outlier verdict");
});

test("forecast keeps a structured 3-to-7-day console output while using the Web model", () => {
  const polygon: [number, number][] = [[0, 0], [100, 0], [100, 60], [0, 60]];
  const planning = solvePlanning(polygon, { refLength: 10, ridgeDistance: 2, samplesPerRound: 3, sporeRadius: 4, rounds: 1, vehicleSpeed: 0.2 });
  const samples = planning.samplingPoints.map((point, index) => ({ ...point, turbidity: 80 + index * 20, pcr_ct: 30 - index, pcr_conc: 1000 * (index + 1), pcr_qual: "valid" as const, pcr_gene: "ITS1-F/ITS4-R", pcr_verdict: index ? "阳性" : "阴性" }));
  const baseline = buildFusionField(polygon, planning, samples, 100, 300);
  const forecast = runForecast(polygon, planning, baseline, {
    windSpeed: 3, windDirection: 90, temperature: 20, humidity: 75, cloud: 20, daytime: true,
    diseaseIndex: 40, lai: 3, plantHeight: 1, soilMoisture: 50, soilTemperature: 18,
    lightIntensity: 20000, rainfall: 0, leafWetness: 60,
  }, [72, 120, 168]);
  assert.deepEqual(Object.keys(forecast), ["72", "120", "168"]);
  for (const slice of Object.values(forecast)) {
    assert.equal(slice.model, "fusion-advection-diffusion");
    assert.equal(slice.stability, "C");
    assert.equal(slice.grid.length, slice.concentrations.length);
    assert.ok(Number.isFinite(slice.peak) && Number.isFinite(slice.p90) && Number.isFinite(slice.mean));
  }
});

test("enhanced Gaussian plume preserves safety-relevant invariants without freezing legacy numbers", () => {
  const source = [0, 0, 1200, 2.5, 0, "C"] as const;
  const downwind = gaussianPlume(...source, 0, -20);
  const crosswind = gaussianPlume(...source, 8, -20);
  const upwind = gaussianPlume(...source, 0, 20);
  assert.equal(upwind, fixture.enhancementBoundary.gaussianPlume.legacySamples.upwind);
  assert.ok(downwind > 0 && crosswind >= 0, "enhanced plume must remain non-negative downwind");
  assert.notEqual(downwind, fixture.enhancementBoundary.gaussianPlume.legacySamples.downwind);
});
